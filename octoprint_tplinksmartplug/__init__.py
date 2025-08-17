# coding=utf-8
from __future__ import absolute_import

import json
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import datetime
from typing import Optional

import flask
import octoprint.plugin
from flask_babel import gettext
from kasa import Device, Discover, Credentials, Module
from octoprint.access.permissions import Permissions, ADMIN_GROUP
from octoprint.events import Events
from octoprint.util import RepeatedTimer
from octoprint.util.version import is_octoprint_compatible
from uptime import uptime

from .worker import AsyncTaskWorker

try:
	from octoprint.util import ResettableTimer
except ImportError:
	class ResettableTimer(threading.Thread):
		def __init__(self, interval, function, args=None, kwargs=None, on_reset=None, on_cancelled=None):
			threading.Thread.__init__(self)
			self._event = threading.Event()
			self._mutex = threading.Lock()
			self.is_reset = True

			if args is None:
				args = []
			if kwargs is None:
				kwargs = dict()

			self.interval = interval
			self.function = function
			self.args = args
			self.kwargs = kwargs
			self.on_cancelled = on_cancelled
			self.on_reset = on_reset

		def run(self):
			while self.is_reset:
				with self._mutex:
					self.is_reset = False
				self._event.wait(self.interval)

			if not self._event.isSet():
				self.function(*self.args, **self.kwargs)
			with self._mutex:
				self._event.set()

		def cancel(self):
			with self._mutex:
				self._event.set()

			if callable(self.on_cancelled):
				self.on_cancelled()

		def reset(self, interval=None):
			with self._mutex:
				if interval:
					self.interval = interval

				self.is_reset = True
				self._event.set()
				self._event.clear()

			if callable(self.on_reset):
				self.on_reset()


class tplinksmartplugPlugin(octoprint.plugin.SettingsPlugin,
							octoprint.plugin.AssetPlugin,
							octoprint.plugin.TemplatePlugin,
							octoprint.plugin.SimpleApiPlugin,
							octoprint.plugin.StartupPlugin,
							octoprint.plugin.ProgressPlugin,
							octoprint.plugin.EventHandlerPlugin,
							octoprint.plugin.ShutdownPlugin):

	def __init__(self):
		self.loaded = None
		self._storage_interface = None
		self.idleTimeoutWaitTemp = None
		self._idleIgnoreCommandsArray = None
		self.idleIgnoreCommands = None
		self.idleTimeout = None
		self._logger = logging.getLogger("octoprint.plugins.tplinksmartplug")
		self._tplinksmartplug_logger = logging.getLogger("octoprint.plugins.tplinksmartplug.debug")
		self.abortTimeout = 0
		self._timeout_value = None
		self._abort_timer = None
		self.print_job_power = 0.0
		self.print_job_started = False
		self._waitForHeaters = False
		self._waitForTimelapse = False
		self._timelapse_active = False
		self._skipIdleTimer = False
		self.powerOffWhenIdle = False
		self._idleTimer = None
		self._autostart_file = None
		self.db_path = None
		self.poll_status = None
		self.power_off_queue = []
		self._gcode_queued = False
		self.active_timers = {"on": {}, "off": {}}
		self.total_correction = 0
		self.last_row = [0, 0, 0, 0, 0, 0, 0]
		self.last_row_entered = False

		# create a thread pool for asyncio tasks
		self.worker = AsyncTaskWorker()

	# ~~ StartupPlugin mixin

	def on_startup(self, host, port):
		# setup customized logger
		from octoprint.logging.handlers import CleaningTimedRotatingFileHandler
		tplinksmartplug_logging_handler = CleaningTimedRotatingFileHandler(
			self._settings.get_plugin_logfile_path(postfix="debug"), when="D", backupCount=3)
		tplinksmartplug_logging_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
		tplinksmartplug_logging_handler.setLevel(logging.DEBUG)

		self._tplinksmartplug_logger.addHandler(tplinksmartplug_logging_handler)
		self._tplinksmartplug_logger.setLevel(
			logging.DEBUG if self._settings.get_boolean(["debug_logging"]) else logging.INFO)
		# self._tplinksmartplug_logger.propagate = False

		self.db_path = os.path.join(self.get_plugin_data_folder(), "energy_data.db")
		if not os.path.exists(self.db_path):
			db = sqlite3.connect(self.db_path)
			cursor = db.cursor()
			cursor.execute(
				'''CREATE TABLE energy_data(id INTEGER PRIMARY KEY, ip TEXT, timestamp DATETIME, voltage REAL, current REAL, power REAL, total REAL, grandtotal REAL)''')
		else:
			db = sqlite3.connect(self.db_path)
			cursor = db.cursor()

		# Update 'energy_data' table schema if 'grandtotal' column not present
		cursor.execute('''SELECT * FROM energy_data''')
		if 'grandtotal' not in next(zip(*cursor.description)):
			# Change type of 'timestamp' to 'DATETIME' (from 'TEXT'), add new 'grandtotal' column
			cursor.execute('''
				ALTER TABLE energy_data RENAME TO _energy_data''')
			cursor.execute('''
				CREATE TABLE energy_data (id INTEGER PRIMARY KEY, ip TEXT, timestamp DATETIME, voltage REAL, current REAL, power REAL, total REAL, grandtotal REAL)''')
			# Copy over table, skipping non-changed values and calculating running grandtotal
			cursor.execute('''
				INSERT INTO energy_data (ip, timestamp, voltage, current, power, total, grandtotal) SELECT ip, timestamp, voltage, current, power, total, grandtotal FROM
					(WITH temptable AS (SELECT *, total - LAG(total,1) OVER(ORDER BY id) AS delta, LAG(power,1) OVER(ORDER BY id) AS power1 FROM _energy_data)
					SELECT *, ROUND(SUM(MAX(delta,0)) OVER (ORDER BY id ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW),6)
					AS grandtotal FROM temptable WHERE power > 0 OR power1 > 0 OR delta <> 0 OR delta IS NULL)''')

			cursor.execute('''DROP TABLE _energy_data''')
			# Compact database
			db.commit()
			cursor.execute('''VACUUM''')

		self.last_row = list(cursor.execute('''SELECT id, timestamp, voltage, current, power, total, grandtotal
			FROM energy_data ORDER BY ROWID DESC LIMIT 1''').fetchone() or [0, 0, 0, 0, 0, 0,
																			0])  # Round to remove floating point imprecision
		self.last_row = self.last_row[:2] + [round(x, 6) for x in self.last_row[2:]]  # Round to correct floating point imprecision in sqlite
		self.last_row_entered = True
		self.total_correction = self.last_row[6] - self.last_row[5]  # grandtotal - total
		db.commit()
		db.close()

	def on_after_startup(self):
		self._logger.info("TPLinkSmartplug loaded!")
		if self._settings.get(["pollingEnabled"]):
			self.poll_status = RepeatedTimer(int(self._settings.get(["pollingInterval"])) * 60, self.check_statuses)
			self.poll_status.start()

		self.abortTimeout = self._settings.get_int(["abortTimeout"])
		self._tplinksmartplug_logger.debug(f"abortTimeout: {self.abortTimeout}")

		self.powerOffWhenIdle = any(map(lambda plug_check: plug_check["automaticShutdownEnabled"] is True, self._settings.get(["arrSmartplugs"])))
		self._tplinksmartplug_logger.debug(f"powerOffWhenIdle: {self.powerOffWhenIdle}")

		self.idleTimeout = self._settings.get_int(["idleTimeout"])
		self._tplinksmartplug_logger.debug(f"idleTimeout: {self.idleTimeout}")
		self.idleIgnoreCommands = self._settings.get(["idleIgnoreCommands"])
		self._idleIgnoreCommandsArray = self.idleIgnoreCommands.replace(" ", "").split(',')
		self._tplinksmartplug_logger.debug(f"idleIgnoreCommands: {self.idleIgnoreCommands}")
		self.idleTimeoutWaitTemp = self._settings.get_int(["idleTimeoutWaitTemp"])
		self._tplinksmartplug_logger.debug(f"idleTimeoutWaitTemp: {self.idleTimeoutWaitTemp}")
		if any(map(lambda plug_check: plug_check["event_on_startup"] is True, self._settings.get(["arrSmartplugs"]))):
			self._tplinksmartplug_logger.debug("powering on due to startup.")
			for plug in self._settings.get(['arrSmartplugs']):
				if plug["event_on_startup"] is True:
					self._tplinksmartplug_logger.debug(f"powering on {plug['ip']} due to startup.")
					response = self.turn_on(plug["ip"])
					if response.get("currentState", False) == "on":
						self._plugin_manager.send_plugin_message(self._identifier, response)
					else:
						self._tplinksmartplug_logger.debug(f"powering on {plug['ip']} during startup failed.")
		self._reset_idle_timer()
		self.loaded = True

	# ~~ ShutdownPlugin mixin

	def on_shutdown(self):
		self.worker.shutdown()

	def on_connect(self, *args, **kwargs):  # Power up on connect
		if not hasattr(self, 'loaded'):
			return None
		if self._settings.get_boolean(["connect_on_connect_request"]) is True:
			self._tplinksmartplug_logger.debug("powering on due to 'Connect' request.")
			for plug in self._settings.get(['arrSmartplugs']):
				if plug["connect_on_connect"] is True and self._printer.is_closed_or_error():
					self._tplinksmartplug_logger.debug(f"powering on {plug['ip']} due to 'Connect' request.")
					response = self.turn_on(plug["ip"])
					if response.get("currentState", False) == "on":
						self._tplinksmartplug_logger.debug(f"powering on {plug['ip']} during 'Connect' succeeded.")
						self._plugin_manager.send_plugin_message(self._identifier, response)
					else:
						self._tplinksmartplug_logger.debug(f"powering on {plug['ip']} during 'Connect' failed.")
		return None

	# ~~ SettingsPlugin mixin

	def get_settings_defaults(self):
		return {'debug_logging': False, 'arrSmartplugs': [], 'pollingInterval': 15, 'pollingEnabled': False,
				'thermal_runaway_monitoring': False, 'thermal_runaway_max_bed': 0, 'thermal_runaway_max_extruder': 0,
				'cost_rate': 0, 'abortTimeout': 30, 'powerOffWhenIdle': False, 'idleTimeout': 30, 'idleIgnoreCommands': 'M105',
				'idleIgnoreHeaters': '', 'idleTimeoutWaitTemp': 50, 'progress_polling': False, 'useDropDown': False,
				'device_configs': {}, 'connect_on_connect_request': False}

	def on_settings_save(self, data):
		old_debug_logging = self._settings.get_boolean(["debug_logging"])
		old_polling_value = self._settings.get_boolean(["pollingEnabled"])
		old_polling_timer = self._settings.get(["pollingInterval"])
		old_power_off_when_idle = self._settings.get_boolean(["powerOffWhenIdle"])

		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

		self.abortTimeout = self._settings.get_int(["abortTimeout"])
		self.powerOffWhenIdle = any(map(lambda plug_check: plug_check["automaticShutdownEnabled"] is True, self._settings.get(["arrSmartplugs"])))

		self.idleTimeout = self._settings.get_int(["idleTimeout"])
		self.idleIgnoreCommands = self._settings.get(["idleIgnoreCommands"])
		self._idleIgnoreCommandsArray = self.idleIgnoreCommands.replace(" ", "").split(',')
		self.idleTimeoutWaitTemp = self._settings.get_int(["idleTimeoutWaitTemp"])

		if self.powerOffWhenIdle != old_power_off_when_idle:
			self._plugin_manager.send_plugin_message(self._identifier,
													 dict(powerOffWhenIdle=self.powerOffWhenIdle, type="timeout",
														  timeout_value=self._timeout_value))

		if self.powerOffWhenIdle:
			self._tplinksmartplug_logger.debug("Settings saved, Automatic Power Off Enabled, starting idle timer...")
			self._reset_idle_timer()

		new_debug_logging = self._settings.get_boolean(["debug_logging"])
		new_polling_value = self._settings.get_boolean(["pollingEnabled"])
		new_polling_timer = self._settings.get(["pollingInterval"])

		if old_debug_logging != new_debug_logging:
			if new_debug_logging:
				self._tplinksmartplug_logger.setLevel(logging.DEBUG)
			else:
				self._tplinksmartplug_logger.setLevel(logging.INFO)

		if old_polling_value != new_polling_value or old_polling_timer != new_polling_timer:
			if self.poll_status is not None:
				self.poll_status.cancel()
				self.poll_status = None

			if new_polling_value:
				self.poll_status = RepeatedTimer(int(self._settings.get(["pollingInterval"])) * 60, self.check_statuses)
				self.poll_status.start()

	def get_settings_version(self):
		return 18

	def on_settings_migrate(self, target, current=None):
		if current is None or current < 5:
			# Reset plug settings to defaults.
			self._tplinksmartplug_logger.debug("Resetting arrSmartplugs for tplinksmartplug settings.")
			self._settings.set(['arrSmartplugs'], self.get_settings_defaults()["arrSmartplugs"])
		elif current == 6:
			# Loop through plug array and set emeter to None
			arr_smartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["emeter"] = None
				arr_smartplugs_new.append(plug)

			self._tplinksmartplug_logger.info("Updating plug array, converting")
			self._tplinksmartplug_logger.info(self._settings.get(['arrSmartplugs']))
			self._tplinksmartplug_logger.info("to")
			self._tplinksmartplug_logger.info(arr_smartplugs_new)
			self._settings.set(["arrSmartplugs"], arr_smartplugs_new)
		elif current == 7:
			# Loop through plug array and set emeter to None
			arr_smartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["emeter"] = dict(get_realtime=False)
				arr_smartplugs_new.append(plug)

			self._tplinksmartplug_logger.info("Updating plug array, converting")
			self._tplinksmartplug_logger.info(self._settings.get(['arrSmartplugs']))
			self._tplinksmartplug_logger.info("to")
			self._tplinksmartplug_logger.info(arr_smartplugs_new)
			self._settings.set(["arrSmartplugs"], arr_smartplugs_new)

		if current is not None and current < 9:
			arr_smartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["thermal_runaway"] = False
				arr_smartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arr_smartplugs_new)

		if current is not None and current < 10:
			arr_smartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["event_on_error"] = False
				plug["event_on_disconnect"] = False
				arr_smartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arr_smartplugs_new)

		if current is not None and current < 11:
			arr_smartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["automaticShutdownEnabled"] = False
				arr_smartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arr_smartplugs_new)

		if current is not None and current < 12:
			arr_smartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["event_on_upload"] = False
				arr_smartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arr_smartplugs_new)

		if current is not None and current < 13:
			arr_smartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["event_on_startup"] = False
				arr_smartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arr_smartplugs_new)

		if current is not None and current < 14:
			arr_smartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				if "/" in plug["ip"]:
					plug_ip, plug_num = plug["ip"].split("/")
					plug["ip"] = "{}/{}".format(plug_ip, int(plug_num) + 1)
				arr_smartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arr_smartplugs_new)

		if current is not None and current < 15:
			arr_smartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["gcodeCmdOn"] = False
				plug["gcodeCmdOff"] = False
				plug["gcodeRunCmdOn"] = ""
				plug["gcodeRunCmdOff"] = ""
				arr_smartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arr_smartplugs_new)

		if current is not None and current < 16:
			arr_smartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["event_on_shutdown"] = False
				arr_smartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arr_smartplugs_new)

		if current is not None and current < 17:
			arr_smartplugs_new = []
			device_configs = {}
			for plug in self._settings.get(['arrSmartplugs']):
				plug["connect_on_connect"] = False
				arr_smartplugs_new.append(plug)
				# attempt to get device_config
				if plug["ip"] != "":
					device_config = self.get_device_config(plug["ip"])
					if device_config:
						device_configs[plug["ip"]] = device_config
			self._settings.set(["device_configs"], device_configs)
			self._settings.set(["arrSmartplugs"], arr_smartplugs_new)

		if current is not None and current < 18:
			arr_smartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["receives_led_commands"] = False
				arr_smartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arr_smartplugs_new)

	# ~~ AssetPlugin mixin

	def get_assets(self):
		css = ["css/fontawesome-iconpicker.css", "css/tplinksmartplug.css"]

		if not is_octoprint_compatible(">=1.5.0"):
			css += ["css/font-awesome.min.css", "css/font-awesome-v4-shims.min.css"]

		return {'js': ["js/jquery-ui.min.js",
					   "js/knockout-sortable.1.2.0.js",
					   "js/fontawesome-iconpicker.js",
					   "js/ko.iconpicker.js",
					   "js/tplinksmartplug.js",
					   "js/knockout-bootstrap.min.js",
					   "js/ko.observableDictionary.js",
					   "js/plotly-latest.min.js"],
				'css': css}

	# ~~ TemplatePlugin mixin

	def is_template_autoescaped(self):
		return True

	def get_template_configs(self):
		templates_to_load = [{'type': "navbar", 'custom_bindings': True, 'classes': ["dropdown"]},
							 {'type': "settings", 'custom_bindings': True},
							 {'type': "sidebar", 'icon': "plug", 'custom_bindings': True,
							  'data_bind': "visible: arrSmartplugs().length > 0",
							  'template': "tplinksmartplug_sidebar.jinja2",
							  'template_header': "tplinksmartplug_sidebar_header.jinja2"},
							 {'type': "tab", 'custom_bindings': True, 'data_bind': "visible: show_sidebar()",
							  'template': "tplinksmartplug_tab.jinja2"}]
		return templates_to_load

	# ~~ ProgressPlugin mixin

	def on_print_progress(self, storage, path, progress):
		if self._settings.get_boolean(["progress_polling"]) is False:
			return
		self._tplinksmartplug_logger.debug(f"Checking statuses during print progress ({progress}).")
		_print_progress_timer = threading.Timer(1, self.check_statuses)
		_print_progress_timer.daemon = True
		_print_progress_timer.start()
		self._plugin_manager.send_plugin_message(self._identifier, dict(updatePlot=True))

		if self.powerOffWhenIdle is True and not (self._skipIdleTimer is True):
			self._tplinksmartplug_logger.debug(f"Resetting idle timer during print progress ({progress})...")
			self._waitForHeaters = False
			self._reset_idle_timer()

	# ~~ SimpleApiPlugin mixin

	async def turn_on_device(self, plug_device) -> Optional[Device]:
		try:
			await plug_device.turn_on()
			await plug_device.update()
			return plug_device
		except Exception as e:
			self._tplinksmartplug_logger.error(f"Failed to turn on {plugip}: {e}")
		return None

	async def turn_off_device(self, plug_device) -> Optional[Device]:
		try:
			await plug_device.turn_off()
			await plug_device.update()
			return plug_device
		except Exception as e:
			self._tplinksmartplug_logger.error(f"Failed to turn on {plugip}: {e}")
		return None

	def turn_on(self, plugip):
		self._tplinksmartplug_logger.debug(f"Turning on {plugip}.")
		try:
			plug_device = self.get_device(plugip)
			future = self.worker.run_coroutine_threadsafe(self.turn_on_device(plug_device))
			plug_device = future.result()
			self._tplinksmartplug_logger.debug(f"Turn on result: {plug_device.is_on}.")
			if plug_device and plug_device.is_on:
				plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
				self._tplinksmartplug_logger.debug(plug)
				if plug["autoConnect"] and self._printer.is_closed_or_error():
					c = threading.Timer(int(plug["autoConnectDelay"]), self._printer.connect)
					c.daemon = True
					c.start()
				if plug["gcodeCmdOn"] and self._printer.is_closed_or_error():
					self._tplinksmartplug_logger.debug("queuing gcode on commands because printer isn't connected yet.")
					self._gcode_queued = True
				if plug["gcodeCmdOn"] and self._printer.is_ready() and plug["gcodeRunCmdOn"] != "":
					self._tplinksmartplug_logger.debug("sending gcode commands to printer.")
					self._printer.commands(plug["gcodeRunCmdOn"].split("\n"))
				if plug["sysCmdOn"]:
					t = threading.Timer(int(plug["sysCmdOnDelay"]), os.system, args=[plug["sysRunCmdOn"]])
					t.daemon = True
					t.start()
				if self.powerOffWhenIdle is True and plug["automaticShutdownEnabled"] is True:
					self._tplinksmartplug_logger.debug(f"Resetting idle timer since plug {plugip} was just turned on.")
					self._waitForHeaters = False
					self._reset_idle_timer()
		except Exception as e:
			self._tplinksmartplug_logger.error(f"Failed to turn on {plugip}: {e}")

		return self.check_status(plugip)

	def turn_off(self, plugip):
		self._tplinksmartplug_logger.debug(f"Turning off {plugip}")
		try:
			plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
			self._tplinksmartplug_logger.debug(plug)
			if plug["gcodeCmdOff"] and plug["gcodeRunCmdOff"] != "":
				self._tplinksmartplug_logger.debug("sending gcode commands to printer.")
				self._printer.commands(plug["gcodeRunCmdOff"].split("\n"))
			if plug["sysCmdOff"]:
				t = threading.Timer(int(plug["sysCmdOffDelay"]), os.system, args=[plug["sysRunCmdOff"]])
				t.daemon = True
				t.start()
			if plug["autoDisconnect"]:
				self._printer.disconnect()
				time.sleep(int(plug["autoDisconnectDelay"]))

			plug_device = self.get_device(plugip)
			future = self.worker.run_coroutine_threadsafe(self.turn_off_device(plug_device))
			plug_device = future.result()
			self._tplinksmartplug_logger.debug(f"Turn off result: {plug_device.is_on}.")

		except Exception as e:
			self._tplinksmartplug_logger.error(f"Failed to turn on {plugip}: {e}")

		return self.check_status(plugip)

	def check_statuses(self):
		for plug in self._settings.get(["arrSmartplugs"]):
			chk = self.check_status(plug["ip"])
			self._plugin_manager.send_plugin_message(self._identifier, chk)

	def check_status(self, plugip):
		self._tplinksmartplug_logger.debug(f"Checking status of {plugip}.")
		emeter_data = None
		today = datetime.today()
		if plugip != "":
			plug_device = self.get_device(plugip)

			if plug_device:
				self._tplinksmartplug_logger.debug(plug_device.state_information)
				chk = plug_device.is_on

				if plug_device.has_emeter:
					v = plug_device.state_information.get("Voltage", 0.0)
					c = plug_device.state_information.get("Current", 0.0)
					p = plug_device.state_information.get("Current consumption", 0.0)
					t = plug_device.state_information.get("Total consumption since reboot", 0.0)

					# fake old response data
					emeter_data = {'get_realtime': {'voltage': v, 'current': c, 'power': p, 'total': t, 'err_code': 0}}

					if self.db_path is not None:
						last_p = self.last_row[4]
						last_t = self.last_row[5]

						if last_t is not None and t < last_t:  # total has reset since last measurement
							self.total_correction += last_t
							emeter_data["get_realtime"]["total"] = round(t + self.total_correction, 6)
						gt = round(t + self.total_correction, 6)  # Prevent accumulated floating-point rounding errors
						current_row = [plugip, today.isoformat(' '), v, c, p, t, gt]

						if self.last_row_entered is False and last_p == 0 and p > 0:  # Go back and enter last_row on power return (if not entered already)
							db = sqlite3.connect(self.db_path)
							cursor = db.cursor()
							cursor.execute(
								'''INSERT INTO energy_data(ip, timestamp, voltage, current, power, total, grandtotal) VALUES(?,?,?,?,?,?,?)''',
								self.last_row)
							db.commit()
							db.close()
							self.last_row_entered = True
						else:
							self.last_row_entered = False

						if t != last_t or p > 0 or last_p > 0:  # Enter current_row if change in total or power is on or just turned off
							db = sqlite3.connect(self.db_path)
							cursor = db.cursor()
							cursor.execute(
								'''INSERT INTO energy_data(ip, timestamp, voltage, current, power, total, grandtotal) VALUES(?,?,?,?,?,?,?)''',
								current_row)
							db.commit()
							db.close()

						self.last_row = current_row

				if chk == 1:
					return dict(currentState="on", emeter=emeter_data, ip=plugip)
				elif chk == 0:
					return dict(currentState="off", emeter=emeter_data, ip=plugip)

		return {'currentState': "unknown", 'emeter': emeter_data, 'ip': plugip}

	def is_api_protected(self):
		return True

	def get_api_commands(self):
		return dict(
			turnOn=["ip"],
			turnOff=["ip"],
			checkStatus=["ip"],
			getEnergyData=["ip"],
			enableAutomaticShutdown=[],
			disableAutomaticShutdown=[],
			abortAutomaticShutdown=[],
			getListPlug=[])

	def on_api_get(self, request):
		if not Permissions.PLUGIN_TPLINKSMARTPLUG_CONTROL.can():
			return flask.make_response("Insufficient rights", 403)

		response = None
		self._tplinksmartplug_logger.debug(request.args)

		if request.args.get("checkStatus"):
			response = self.check_status(request.args.get("checkStatus"))

		return flask.jsonify(response)

	def on_api_command(self, command, data):
		if not Permissions.PLUGIN_TPLINKSMARTPLUG_CONTROL.can():
			return flask.make_response("Insufficient rights", 403)

		response = None

		if command == 'turnOn':
			response = self.turn_on("{ip}".format(**data))
			self._plugin_manager.send_plugin_message(self._identifier, response)
		elif command == 'turnOff':
			response = self.turn_off("{ip}".format(**data))
			self._plugin_manager.send_plugin_message(self._identifier, response)
		elif command == 'checkStatus':
			response = self.check_status("{ip}".format(**data))
		elif command == 'getEnergyData':
			db = sqlite3.connect(self.db_path)
			cursor = db.cursor()
			cursor.execute(
				'''SELECT timestamp, current, power, grandtotal, voltage FROM energy_data WHERE ip=? ORDER BY timestamp DESC LIMIT ?,?''',
				(data["ip"], data["record_offset"], data["record_limit"]))
			response = {'energy_data': cursor.fetchall()}
			db.close()
			self._tplinksmartplug_logger.debug(response)
		# SELECT * FROM energy_data WHERE ip = '192.168.0.102' LIMIT 0,30
		elif command == 'enableAutomaticShutdown':
			self.powerOffWhenIdle = True
			self._reset_idle_timer()
		elif command == 'disableAutomaticShutdown':
			self.powerOffWhenIdle = False
			self._stop_idle_timer()
			if self._abort_timer is not None:
				self._abort_timer.cancel()
				self._abort_timer = None
			self._timeout_value = None
		elif command == 'abortAutomaticShutdown':
			if self._abort_timer is not None:
				self._abort_timer.cancel()
				self._abort_timer = None
			self._timeout_value = None
			self._tplinksmartplug_logger.debug("Power off aborted.")
			self._tplinksmartplug_logger.debug("Restarting idle timer.")
			self._reset_idle_timer()
		elif command == "getListPlug":
			return json.dumps(self._settings.get(["arrSmartplugs"]))
		else:
			response = dict(ip="{ip}".format(**data), currentState="unknown")
		if command == "enableAutomaticShutdown" or command == "disableAutomaticShutdown":
			self._tplinksmartplug_logger.debug(f"Automatic power off setting changed: {self.powerOffWhenIdle}")
			self._settings.set_boolean(["powerOffWhenIdle"], self.powerOffWhenIdle)
			self._settings.save()
		if command == "enableAutomaticShutdown" or command == "disableAutomaticShutdown" or command == "abortAutomaticShutdown":
			self._plugin_manager.send_plugin_message(self._identifier,
													 dict(powerOffWhenIdle=self.powerOffWhenIdle, type="timeout",
														  timeout_value=self._timeout_value))

		return flask.jsonify(response)

	# ~~ EventHandlerPlugin mixin

	def on_event(self, event, payload):
		# Startup Event
		if event == Events.STARTUP and any(map(lambda plug_check: plug_check["event_on_startup"] is True, self._settings.get(["arrSmartplugs"]))) is True:
			self._tplinksmartplug_logger.debug(f"powering on due to {event} event.")
			for plug in self._settings.get(['arrSmartplugs']):
				if plug["event_on_startup"] is True:
					self._tplinksmartplug_logger.debug(f"powering on {plug['ip']} due to {event} event.")
					response = self.turn_on(plug["ip"])
					if response["currentState"] == "on":
						self._plugin_manager.send_plugin_message(self._identifier, response)
		# Error Event
		if event == Events.ERROR and any(map(lambda plug_check: plug_check["event_on_error"] is True, self._settings.get(["arrSmartplugs"]))) is True:
			self._tplinksmartplug_logger.debug(f"powering off due to {event} event.")
			for plug in self._settings.get(['arrSmartplugs']):
				if plug["event_on_error"] is True:
					self._tplinksmartplug_logger.debug(f"powering off {plug['ip']} due to {event} event.")
					response = self.turn_off(plug["ip"])
					if response["currentState"] == "off":
						self._plugin_manager.send_plugin_message(self._identifier, response)
		# Client Opened Event
		if event == Events.CLIENT_OPENED:
			if any(map(lambda plug_check: plug_check["automaticShutdownEnabled"] is True, self._settings.get(["arrSmartplugs"]))):
				self._tplinksmartplug_logger.debug(f"resetting idle timer due to {event} event.")
				self._reset_idle_timer()
			self._plugin_manager.send_plugin_message(self._identifier,
													 dict(powerOffWhenIdle=self.powerOffWhenIdle, type="timeout",
														  timeout_value=self._timeout_value))
			return
		# Canceled Print Interpreted Event
		if event == Events.PRINT_FAILED and not self._printer.is_closed_or_error():
			self._tplinksmartplug_logger.debug("Print cancelled, resetting job_power to 0")
			self.print_job_power = 0.0
			self.print_job_started = False
			self._autostart_file = None
			return
		# Print Started Event
		if event == Events.PRINT_STARTED and self._settings.get_float(["cost_rate"]) > 0:
			self.print_job_started = True
			self._tplinksmartplug_logger.debug(payload.get("path", None))
			for plug in self._settings.get(["arrSmartplugs"]):
				status = self.check_status(plug["ip"])
				self.print_job_power -= float(
					self.deep_get(status, ["emeter", "get_realtime", "total_wh"], default=0)) / 1000
				self.print_job_power -= float(self.deep_get(status, ["emeter", "get_realtime", "total"], default=0))
				self._tplinksmartplug_logger.debug(self.print_job_power)

		if event == Events.PRINT_STARTED and self.powerOffWhenIdle is True:
			if self._abort_timer is not None:
				self._abort_timer.cancel()
				self._abort_timer = None
				self._tplinksmartplug_logger.debug("Power off aborted because starting new print.")
			if self._idleTimer is not None:
				self._reset_idle_timer()
			self._timeout_value = None
			self._plugin_manager.send_plugin_message(self._identifier,
													 dict(powerOffWhenIdle=self.powerOffWhenIdle, type="timeout",
														  timeout_value=self._timeout_value))

		# Print Done Event
		if event == Events.PRINT_DONE and self.print_job_started:
			self._tplinksmartplug_logger.debug(payload)

			for plug in self._settings.get(["arrSmartplugs"]):
				status = self.check_status(plug["ip"])
				self.print_job_power += float(
					self.deep_get(status, ["emeter", "get_realtime", "total_wh"], default=0)) / 1000
				self.print_job_power += float(self.deep_get(status, ["emeter", "get_realtime", "total"], default=0))
				self._tplinksmartplug_logger.debug(self.print_job_power)

			hours = (payload.get("time", 0) / 60) / 60
			self._tplinksmartplug_logger.debug(f"hours: {hours}")
			power_used = self.print_job_power
			self._tplinksmartplug_logger.debug(f"power used: {power_used}")
			power_cost = power_used * self._settings.get_float(["cost_rate"])
			self._tplinksmartplug_logger.debug(f"power total cost: {power_cost}")

			self._storage_interface = self._file_manager._storage(payload.get("origin", "local"))
			self._storage_interface.set_additional_metadata(payload.get("path"), "statistics", dict(
				lastPowerCost=dict(_default=float('{:.4f}'.format(power_cost)))), merge=True)

			self.print_job_power = 0.0
			self.print_job_started = False
			self._autostart_file = None

		if event == Events.PRINT_DONE and len(self.power_off_queue) > 0:
			self._tplinksmartplug_logger.debug(f"power_off_queue: {self.power_off_queue}")
			for plug in self.power_off_queue:
				chk = self.turn_off(plug["ip"])
				self._plugin_manager.send_plugin_message(self._identifier, chk)
			self.power_off_queue = []

		if self.powerOffWhenIdle is True and event == Events.MOVIE_RENDERING:
			self._tplinksmartplug_logger.debug(f"Timelapse generation started: {payload.get('movie_basename', '')}")
			self._timelapse_active = True

		if self._timelapse_active and event == Events.MOVIE_DONE or event == Events.MOVIE_FAILED:
			self._tplinksmartplug_logger.debug(
				f"Timelapse generation finished: {payload.get('movie_basename', '')}. Return Code: {payload.get('returncode', 'completed')}")
			self._timelapse_active = False
		# Printer Connected Event
		if event == Events.CONNECTED:
			if self._gcode_queued:
				for plug in self._settings.get(['arrSmartplugs']):
					if plug["gcodeCmdOn"] and plug["gcodeRunCmdOn"] != "":
						self._tplinksmartplug_logger.debug("sending gcode commands to printer.")
						self._printer.commands(plug["gcodeRunCmdOn"].split("\n"))
				self._gcode_queued = False
			if self._autostart_file:
				self._tplinksmartplug_logger.debug(f"printer connected starting print of {self._autostart_file}")
				self._printer.select_file(self._autostart_file, False, printAfterSelect=True)
				self._autostart_file = None
		# File Uploaded Event
		if event == Events.UPLOAD and any(map(lambda plug_check: plug_check["event_on_upload"] is True, self._settings.get(["arrSmartplugs"]))) is True:
			self._tplinksmartplug_logger.debug(f"File uploaded: {payload.get('name', '')}. Turning enabled plugs on.")
			self._tplinksmartplug_logger.debug(payload)
			for plug in self._settings.get(['arrSmartplugs']):
				self._tplinksmartplug_logger.debug(plug)
				if plug["event_on_upload"] is True and self._printer.is_closed_or_error():
					self._tplinksmartplug_logger.debug(f"powering on {plug['ip']} due to {event} event.")
					response = self.turn_on(plug["ip"])
					if response["currentState"] == "on":
						self._tplinksmartplug_logger.debug(f"power on successful for {plug['ip']} attempting connection in {plug.get('autoConnectDelay', '0')} seconds")
						self._plugin_manager.send_plugin_message(self._identifier, response)
						if payload.get("path", False) and payload.get("target") == "local" and payload.get("print", False):
							self._autostart_file = payload.get("path")
		# Shutdown Event
		if event == Events.SHUTDOWN and any(map(lambda plug_check: plug_check["event_on_shutdown"] is True, self._settings.get(["arrSmartplugs"]))) is True:
			for plug in self._settings.get(['arrSmartplugs']):
				if plug["event_on_shutdown"] is True:
					self._tplinksmartplug_logger.debug(f"powering off {plug['ip']} due to shutdown event.")
					self.turn_off(plug["ip"])

	# ~~ Idle Timeout

	def _start_idle_timer(self):
		self._stop_idle_timer()

		if self.powerOffWhenIdle:
			self._idleTimer = ResettableTimer(self.idleTimeout * 60, self._idle_poweroff)
			self._idleTimer.daemon = True
			self._idleTimer.start()

	def _stop_idle_timer(self):
		if self._idleTimer:
			self._idleTimer.cancel()
			self._idleTimer = None

	def _reset_idle_timer(self):
		try:
			if self._idleTimer.is_alive():
				self._idleTimer.reset()
			else:
				raise Exception()
		except Exception as e:
			self._tplinksmartplug_logger.error(f"idle timer exception: {e}")
			self._start_idle_timer()

	def _idle_poweroff(self):
		if not self.powerOffWhenIdle:
			return

		if self._waitForHeaters:
			return

		if self._waitForTimelapse:
			return

		if self._printer.is_printing() or self._printer.is_paused():
			return

		if (uptime() / 60) <= (self._settings.get_int(["idleTimeout"])):
			self._tplinksmartplug_logger.debug("Just booted so wait for time sync.")
			self._tplinksmartplug_logger.debug(
				"uptime: {}, comparison: {}".format((uptime() / 60), (self._settings.get_int(["idleTimeout"]))))
			self._reset_idle_timer()
			return

		self._tplinksmartplug_logger.debug(
			"Idle timeout reached after %s minute(s). Turning heaters off prior to powering off plugs." % self.idleTimeout)
		if self._wait_for_heaters():
			self._tplinksmartplug_logger.debug("Heaters below temperature.")
			self._tplinksmartplug_logger.debug("Checking for timelapse running.")
			if self._wait_for_timelapse():
				if self._printer.is_printing() or self._printer.is_paused():
					self._tplinksmartplug_logger.debug("Aborted power off due to print activity.")
					return
				self._timer_start()
		else:
			self._tplinksmartplug_logger.debug("Aborted power off due to activity.")

	# ~~ Timelapse Monitoring

	def _wait_for_timelapse(self):
		self._waitForTimelapse = True
		self._tplinksmartplug_logger.debug("Checking timelapse status before shutting off power...")

		while True:
			if not self._waitForTimelapse:
				return False

			if not self._timelapse_active:
				self._waitForTimelapse = False
				return True

			self._tplinksmartplug_logger.debug("Waiting for timelapse before shutting off power...")
			time.sleep(5)

	# ~~ Temperature Cooldown

	def _wait_for_heaters(self):
		self._waitForHeaters = True
		heaters = self._printer.get_current_temperatures()
		ignored_heaters = self._settings.get(["idleIgnoreHeaters"]).replace(" ", "").split(',')

		for heater, entry in heaters.items():
			target = entry.get("target")
			if target is None or heater in ignored_heaters:
				# heater doesn't exist in fw or set to be ignored
				continue

			try:
				temp = float(target)
			except ValueError:
				# not a float for some reason, skip it
				continue

			if temp != 0:
				self._tplinksmartplug_logger.debug(f"Turning off heater: {heater}")
				self._skipIdleTimer = True
				self._printer.set_temperature(heater, 0)
				self._skipIdleTimer = False
			else:
				self._tplinksmartplug_logger.debug(f"Heater {heater} already off.")

		while True:
			if not self._waitForHeaters:
				return False

			heaters = self._printer.get_current_temperatures()

			highest_temp = 0
			heaters_above_waittemp = []
			for heater, entry in heaters.items():
				if not heater.startswith("tool") or heater in ignored_heaters:
					continue

				actual = entry.get("actual")
				if actual is None:
					# heater doesn't exist in fw
					continue

				try:
					temp = float(actual)
				except ValueError:
					# not a float for some reason, skip it
					continue

				self._tplinksmartplug_logger.debug(f"Heater {heater} = {temp}C")
				if temp > self.idleTimeoutWaitTemp:
					heaters_above_waittemp.append(heater)

				if temp > highest_temp:
					highest_temp = temp

			if highest_temp <= self.idleTimeoutWaitTemp:
				self._waitForHeaters = False
				return True

			self._tplinksmartplug_logger.debug(
				"Waiting for heaters(%s) before shutting power off..." % ', '.join(heaters_above_waittemp))
			time.sleep(5)

	# ~~ Abort Power Off Timer

	def _timer_start(self):
		if self._abort_timer is not None:
			return

		self._tplinksmartplug_logger.debug("Starting abort power off timer.")

		self._timeout_value = self.abortTimeout
		self._abort_timer = RepeatedTimer(1, self._timer_task)
		self._abort_timer.start()

	def _timer_task(self):
		if self._timeout_value is None:
			return

		self._timeout_value -= 1
		self._plugin_manager.send_plugin_message(self._identifier,
												 dict(powerOffWhenIdle=self.powerOffWhenIdle, type="timeout",
													  timeout_value=self._timeout_value))
		if self._timeout_value <= 0:
			if self._abort_timer is not None:
				self._abort_timer.cancel()
				self._abort_timer = None
			self._shutdown_system()

	def _shutdown_system(self):
		self._tplinksmartplug_logger.debug("Automatically powering off enabled plugs.")
		for plug in self._settings.get(['arrSmartplugs']):
			if plug.get("automaticShutdownEnabled", False):
				response = self.turn_off("{ip}".format(**plug))
				self._plugin_manager.send_plugin_message(self._identifier, response)
		self._stop_idle_timer()

	# ~~ Utilities

	def rgb2hsv(self, r, g, b):
		r, g, b = r/255.0, g/255.0, b/255.0
		return_val = dict()
		mx = max(r, g, b)
		mn = min(r, g, b)
		df = mx-mn
		if mx == mn:
			return_val["hue"] = 0
		elif mx == r:
			return_val["hue"] = (60 * ((g-b)/df) + 360) % 360
		elif mx == g:
			return_val["hue"] = (60 * ((b-r)/df) + 120) % 360
		elif mx == b:
			return_val["hue"] = (60 * ((r-g)/df) + 240) % 360
		if mx == 0:
			return_val["saturation"] = 0
		else:
			return_val["saturation"] = df/mx * 100
		return_val["value"] = mx
		return return_val

	def get_device_config(self, plugip: str):
		device_configs = self._settings.get(["device_configs"])
		config_dict = device_configs.get(plugip, None)
		username = self._settings.get(["username"])
		password = self._settings.get(["password"])

		if not config_dict:  # config is not saved, add it to settings
			try:
				plug_ip = plugip.split("/")
				future = self.worker.run_coroutine_threadsafe(
					Discover.discover_single(plug_ip[0], username=username, password=password))
				device = future.result()
				config_dict = device.config.to_dict()
				if config_dict:
					if "credentials" in config_dict:  # remove credentials from config to avoid yaml save error
						config_dict["credentials"] = {"username": username, "password": password}
					device_configs[plugip] = config_dict
					self._settings.set(["device_configs"], device_configs)
					self._settings.save()
			except Exception as e:
				self._tplinksmartplug_logger.debug(f"Unable to get device_config for {plugip}: {e}")
		return config_dict

	async def connect_device(self, config_dict):
		try:
			if "credentials" in config_dict:
				config_dict["credentials"] = Credentials(**config_dict["credentials"])

			device = await Device.connect(config=Device.Config.from_dict(config_dict))
			await device.update()
			return device
		except Exception as e:
			self._tplinksmartplug_logger.error(f"Error connecting to device: {e}")
		return None

	async def set_device_led(self, device, led_values, set_color=False) -> Optional[Device]:
		try:
			self._tplinksmartplug_logger.debug(f"Setting led from values: {led_values}")
			light = device.modules[Module.Light]
			if light:
				if not device.is_on and led_values["LEDOn"]:  # turn light on if off
					await device.turn_on()
				elif device.is_on and not led_values["LEDOn"]:
					await device.turn_off()
					await device.update()
					return device
				if "hsv" in device.features and set_color:
					hsv_values = self.rgb2hsv(led_values["LEDRed"], led_values["LEDGreen"], led_values["LEDBlue"])
					self._tplinksmartplug_logger.debug(f"Setting hsv values: {hsv_values}")
					await light.set_hsv(int(hsv_values["hue"]), int(hsv_values["saturation"]), int(hsv_values["value"]))
				if light.brightness != int(led_values["LEDBrightness"]):
					await light.set_brightness(int(led_values["LEDBrightness"]))
				await device.update()
		except Exception as e:
			self._tplinksmartplug_logger.error(f"Error connecting to device: {e}")
		return device

	def get_device(self, plugip: str) -> Optional[Device]:
		try:
			config_dict = self.get_device_config(plugip)
			future = self.worker.run_coroutine_threadsafe(self.connect_device(config_dict))
			device = future.result()
			plug_ip = plugip.split("/")
			if len(plug_ip) == 2 and len(device.children) > 0:
				device = device.children[int(plug_ip[1]) - 1]
			return device
		except Exception as e:
			self._tplinksmartplug_logger.error(f"Error connecting to device: {e}")
		return None

	def deep_get(self, d, keys, default=None):
		"""
		Example:
			d = {'meta': {'status': 'OK', 'status_code': 200}}
			deep_get(d, ['meta', 'status_code'])		  # => 200
			deep_get(d, ['garbage', 'status_code'])	   # => None
			deep_get(d, ['meta', 'garbage'], default='-') # => '-'
		"""
		assert type(keys) is list
		if d is None:
			return default
		if not keys:
			return d
		return self.deep_get(d.get(keys[0]), keys[1:], default)

	def lookup(self, dic, key, *keys):
		if keys:
			return self.lookup(dic.get(key, {}), *keys)
		return dic.get(key)

	@staticmethod
	def plug_search(plug_list, key, value):
		for item in plug_list:
			if item[key] == value.strip():
				return item
		return None

	# ~~ Gcode processing hook

	def gcode_turn_off(self, plug):
		if plug["ip"] in self.active_timers["off"]:
			self.active_timers["off"][plug["ip"]].cancel()
			del self.active_timers["off"][plug["ip"]]

		if self._printer.is_printing() and plug["warnPrinting"] is True:
			self._tplinksmartplug_logger.debug(
				"Not powering off %s immediately because printer is printing." % plug["label"])
			self.power_off_queue.append(plug)
		else:
			chk = self.turn_off(plug["ip"])
			self._plugin_manager.send_plugin_message(self._identifier, chk)

	def gcode_turn_on(self, plug):
		if plug["ip"] in self.active_timers["on"]:
			self.active_timers["on"][plug["ip"]].cancel()
			del self.active_timers["on"][plug["ip"]]

		chk = self.turn_on(plug["ip"])
		self._plugin_manager.send_plugin_message(self._identifier, chk)

	def process_gcode(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
		if self.powerOffWhenIdle and not (gcode in self._idleIgnoreCommandsArray):
			self._waitForHeaters = False
			self._reset_idle_timer()

		if gcode not in ["M80", "M81", "M150", "M355"]:
			return

		if gcode == "M80":
			plugip = re.sub(r'^M80\s?', '', cmd)
			self._tplinksmartplug_logger.debug(f"Received M80 command, attempting power on of {plugip}.")
			plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
			self._tplinksmartplug_logger.debug(plug)
			if plug and plug["gcodeEnabled"]:
				t = threading.Timer(int(plug["gcodeOnDelay"]), self.gcode_turn_on, [plug])
				t.daemon = True
				t.start()
			return
		elif gcode == "M81":
			plugip = re.sub(r'^M81\s?', '', cmd)
			self._tplinksmartplug_logger.debug(f"Received M81 command, attempting power off of {plugip}.")
			plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
			self._tplinksmartplug_logger.debug(plug)
			if plug and plug["gcodeEnabled"]:
				t = threading.Timer(int(plug["gcodeOffDelay"]), self.gcode_turn_off, [plug])
				t.daemon = True
				t.start()
			return
		elif gcode in ["M150", "M355"] and any(map(lambda plug_check: plug_check["receives_led_commands"] is True, self._settings.get(["arrSmartplugs"]))):
			for led_device in self._settings.get(["arrSmartplugs"]):
				if led_device["receives_led_commands"]:
					device = self.get_device(led_device["ip"])
					if device:
						led_values = {'LEDRed': 255, 'LEDBlue': 255, 'LEDGreen': 255, 'LEDWhite': 255, 'LEDBrightness': 100, 'LEDOn': True}
						cmd_split = cmd.upper().split()
						for i in cmd_split:
							first_char = str(i[0].upper())
							led_data = str(i[1:].strip())
							if not led_data.isdigit() and first_char != 'I':
								self._tplinksmartplug_logger.debug(led_data)
								return

							if first_char == 'M':
								continue
							elif first_char == 'R':
								led_values['LEDRed'] = int(led_data)
							elif first_char == 'B':
								led_values['LEDBlue'] = int(led_data)
							elif first_char == 'G' or first_char == 'U':
								led_values['LEDGreen'] = int(led_data)
							elif first_char == "W":
								led_values['LEDWhite'] = int(led_data)
							elif first_char == "P":
								led_values['LEDBrightness'] = int(float(led_data) / 255 * 100)
							elif first_char == "S":
								led_values['LEDOn'] = bool(int(led_data))
							else:
								self._tplinksmartplug_logger.debug(led_data)

						self._tplinksmartplug_logger.debug(f"M150 command, attempting color change of {led_device['ip']}.")
						self.worker.run_coroutine_threadsafe(self.set_device_led(device, led_values, set_color=(gcode == "M150")))
			return

	def process_at_command(self, comm_instance, phase, command, parameters, tags=None, *args, **kwargs):
		if command == "TPLINKON":
			plugip = parameters
			self._tplinksmartplug_logger.debug(f"Received TPLINKON command, attempting power on of {plugip}.")
			plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
			self._tplinksmartplug_logger.debug(plug)
			if plug and plug["gcodeEnabled"]:
				if plugip in self.active_timers["off"]:
					self.active_timers["off"][plugip].cancel()
					del self.active_timers["off"][plugip]
				self.active_timers["on"][plugip] = threading.Timer(int(plug["gcodeOnDelay"]), self.gcode_turn_on,
																   [plug])
				self.active_timers["on"][plugip].daemon = True
				self.active_timers["on"][plugip].start()
		elif command == "TPLINKOFF":
			plugip = parameters
			self._tplinksmartplug_logger.debug(f"Received TPLINKOFF command, attempting power off of {plugip}.")
			plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
			self._tplinksmartplug_logger.debug(plug)
			if plug and plug["gcodeEnabled"]:
				if plugip in self.active_timers["on"]:
					self.active_timers["on"][plugip].cancel()
					del self.active_timers["on"][plugip]
				self.active_timers["off"][plugip] = threading.Timer(int(plug["gcodeOffDelay"]), self.gcode_turn_off,
																	[plug])
				self.active_timers["off"][plugip].daemon = True
				self.active_timers["off"][plugip].start()
		elif command in ["TPLINKIDLEON", "TPLINKIDLEOFF"]:
			if command == 'TPLINKIDLEON':
				self.powerOffWhenIdle = True
				self._reset_idle_timer()
			elif command == 'TPLINKIDLEOFF':
				self.powerOffWhenIdle = False
				self._stop_idle_timer()
				if self._abort_timer is not None:
					self._abort_timer.cancel()
					self._abort_timer = None
				self._timeout_value = None
			self._plugin_manager.send_plugin_message(self._identifier,
													 dict(powerOffWhenIdle=self.powerOffWhenIdle, type="timeout",
														  timeout_value=self._timeout_value))

	# ~~ Temperatures received hook

	def check_temps(self, parsed_temps):
		thermal_runaway_triggered = False
		for k, v in list(parsed_temps.items()):
			if k == "B" and v[0] > int(self._settings.get(["thermal_runaway_max_bed"])):
				self._tplinksmartplug_logger.debug("Max bed temp reached, shutting off plugs.")
				thermal_runaway_triggered = True
			if k.startswith("T") and v[0] > int(self._settings.get(["thermal_runaway_max_extruder"])):
				self._tplinksmartplug_logger.debug("Extruder max temp reached, shutting off plugs.")
				thermal_runaway_triggered = True
			if thermal_runaway_triggered:
				for plug in self._settings.get(['arrSmartplugs']):
					if plug["thermal_runaway"]:
						response = self.turn_off(plug["ip"])
						if response["currentState"] == "off":
							self._plugin_manager.send_plugin_message(self._identifier, response)

	def monitor_temperatures(self, comm, parsed_temps):
		if self._settings.get(["thermal_runaway_monitoring"]):
			# Run inside it's own thread to prevent communication blocking
			t = threading.Timer(0, self.check_temps, [parsed_temps])
			t.daemon = True
			t.start()
		return parsed_temps

	# ~~ Access Permissions Hook

	@staticmethod
	def get_additional_permissions(*args, **kwargs):
		return [
			dict(key="CONTROL",
				 name="Control Plugs",
				 description=gettext("Allows control of configured plugs."),
				 roles=["admin"],
				 dangerous=True,
				 default_groups=[ADMIN_GROUP])
		]

	# ~~ Softwareupdate hook

	def get_update_information(self):
		return dict(
			tplinksmartplug=dict(
				displayName="TP-Link Smartplug",
				displayVersion=self._plugin_version,
				type="github_release",
				user="jneilliii",
				repo="OctoPrint-TPLinkSmartplug",
				current=self._plugin_version,
				stable_branch=dict(
					name="Stable", branch="master", comittish=["master"]
				),
				prerelease_branches=[
					dict(
						name="Release Candidate",
						branch="rc",
						comittish=["rc", "master"],
					)
				],
				pip="https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/archive/{target_version}.zip"
			)
		)


__plugin_name__ = "TP-Link Smartplug"
__plugin_pythoncompat__ = ">=2.7,<4"


def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = tplinksmartplugPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.comm.protocol.gcode.queuing": __plugin_implementation__.process_gcode,
		"octoprint.comm.protocol.atcommand.sending": __plugin_implementation__.process_at_command,
		"octoprint.comm.protocol.temperatures.received": __plugin_implementation__.monitor_temperatures,
		"octoprint.access.permissions": __plugin_implementation__.get_additional_permissions,
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information,
		"octoprint.printer.handle_connect": __plugin_implementation__.on_connect
	}
