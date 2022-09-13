# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.access.permissions import Permissions, ADMIN_GROUP
from octoprint.events import Events
from octoprint.util import RepeatedTimer
from flask_babel import gettext
import socket
import json
import flask
import logging
import os
import re
import threading
import time
import sqlite3

from octoprint.util.version import is_octoprint_compatible
from uptime import uptime
from datetime import datetime
from struct import unpack
from builtins import bytes

try:
	from octoprint.util import ResettableTimer
except:
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
							octoprint.plugin.EventHandlerPlugin):

	def __init__(self):
		self._logger = logging.getLogger("octoprint.plugins.tplinksmartplug")
		self._tplinksmartplug_logger = logging.getLogger("octoprint.plugins.tplinksmartplug.debug")
		self.abortTimeout = 0
		self._timeout_value = None
		self._abort_timer = None
		self._countdown_active = False
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

	##~~ StartupPlugin mixin

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
		self._tplinksmartplug_logger.propagate = False

		self.db_path = os.path.join(self.get_plugin_data_folder(), "energy_data.db")
		if not os.path.exists(self.db_path):
			db = sqlite3.connect(self.db_path)
			cursor = db.cursor()
			cursor.execute(
				'''CREATE TABLE energy_data(id INTEGER PRIMARY KEY, ip TEXT, timestamp TEXT, current REAL, power REAL, total REAL, voltage REAL)''')
			db.commit()
			db.close()

	def on_after_startup(self):
		self._logger.info("TPLinkSmartplug loaded!")
		if self._settings.get(["pollingEnabled"]):
			self.poll_status = RepeatedTimer(int(self._settings.get(["pollingInterval"])) * 60, self.check_statuses)
			self.poll_status.start()

		self.abortTimeout = self._settings.get_int(["abortTimeout"])
		self._tplinksmartplug_logger.debug("abortTimeout: %s" % self.abortTimeout)

		self.powerOffWhenIdle = self._settings.get_boolean(["powerOffWhenIdle"])
		self._tplinksmartplug_logger.debug("powerOffWhenIdle: %s" % self.powerOffWhenIdle)

		self.idleTimeout = self._settings.get_int(["idleTimeout"])
		self._tplinksmartplug_logger.debug("idleTimeout: %s" % self.idleTimeout)
		self.idleIgnoreCommands = self._settings.get(["idleIgnoreCommands"])
		self._idleIgnoreCommandsArray = self.idleIgnoreCommands.split(',')
		self._tplinksmartplug_logger.debug("idleIgnoreCommands: %s" % self.idleIgnoreCommands)
		self.idleTimeoutWaitTemp = self._settings.get_int(["idleTimeoutWaitTemp"])
		self._tplinksmartplug_logger.debug("idleTimeoutWaitTemp: %s" % self.idleTimeoutWaitTemp)
		if self._settings.get_boolean(["event_on_startup_monitoring"]) is True:
			self._tplinksmartplug_logger.debug("powering on due to startup.")
			for plug in self._settings.get(['arrSmartplugs']):
				if plug["event_on_startup"] is True:
					self._tplinksmartplug_logger.debug("powering on %s due to startup." % (plug["ip"]))
					response = self.turn_on(plug["ip"])
					if response.get("currentState", False) == "on":
						self._plugin_manager.send_plugin_message(self._identifier, response)
					else:
						self._tplinksmartplug_logger.debug("powering on %s during startup failed." % (plug["ip"]))
		self._reset_idle_timer()

	##~~ SettingsPlugin mixin

	def get_settings_defaults(self):
		return {'debug_logging': False, 'arrSmartplugs': [], 'pollingInterval': 15, 'pollingEnabled': False,
				'thermal_runaway_monitoring': False, 'thermal_runaway_max_bed': 0, 'thermal_runaway_max_extruder': 0,
				'event_on_error_monitoring': False, 'event_on_disconnect_monitoring': False,
				'event_on_upload_monitoring': False, 'event_on_upload_monitoring_always': False,
				'event_on_startup_monitoring': False, 'event_on_shutdown_monitoring': False, 'cost_rate': 0,
				'abortTimeout': 30, 'powerOffWhenIdle': False, 'idleTimeout': 30, 'idleIgnoreCommands': 'M105',
				'idleTimeoutWaitTemp': 50, 'progress_polling': False, 'useDropDown': False}

	def on_settings_save(self, data):
		old_debug_logging = self._settings.get_boolean(["debug_logging"])
		old_polling_value = self._settings.get_boolean(["pollingEnabled"])
		old_polling_timer = self._settings.get(["pollingInterval"])
		old_powerOffWhenIdle = self._settings.get_boolean(["powerOffWhenIdle"])
		old_idleTimeout = self._settings.get_int(["idleTimeout"])
		old_idleIgnoreCommands = self._settings.get(["idleIgnoreCommands"])
		old_idleTimeoutWaitTemp = self._settings.get_int(["idleTimeoutWaitTemp"])

		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

		self.abortTimeout = self._settings.get_int(["abortTimeout"])
		self.powerOffWhenIdle = self._settings.get_boolean(["powerOffWhenIdle"])

		self.idleTimeout = self._settings.get_int(["idleTimeout"])
		self.idleIgnoreCommands = self._settings.get(["idleIgnoreCommands"])
		self._idleIgnoreCommandsArray = self.idleIgnoreCommands.split(',')
		self.idleTimeoutWaitTemp = self._settings.get_int(["idleTimeoutWaitTemp"])

		if self.powerOffWhenIdle != old_powerOffWhenIdle:
			self._plugin_manager.send_plugin_message(self._identifier,
													 dict(powerOffWhenIdle=self.powerOffWhenIdle, type="timeout",
														  timeout_value=self._timeout_value))

		if self.powerOffWhenIdle == True:
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
		return 16

	def on_settings_migrate(self, target, current=None):
		if current is None or current < 5:
			# Reset plug settings to defaults.
			self._tplinksmartplug_logger.debug("Resetting arrSmartplugs for tplinksmartplug settings.")
			self._settings.set(['arrSmartplugs'], self.get_settings_defaults()["arrSmartplugs"])
		elif current == 6:
			# Loop through plug array and set emeter to None
			arrSmartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["emeter"] = None
				arrSmartplugs_new.append(plug)

			self._tplinksmartplug_logger.info("Updating plug array, converting")
			self._tplinksmartplug_logger.info(self._settings.get(['arrSmartplugs']))
			self._tplinksmartplug_logger.info("to")
			self._tplinksmartplug_logger.info(arrSmartplugs_new)
			self._settings.set(["arrSmartplugs"], arrSmartplugs_new)
		elif current == 7:
			# Loop through plug array and set emeter to None
			arrSmartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["emeter"] = dict(get_realtime=False)
				arrSmartplugs_new.append(plug)

			self._tplinksmartplug_logger.info("Updating plug array, converting")
			self._tplinksmartplug_logger.info(self._settings.get(['arrSmartplugs']))
			self._tplinksmartplug_logger.info("to")
			self._tplinksmartplug_logger.info(arrSmartplugs_new)
			self._settings.set(["arrSmartplugs"], arrSmartplugs_new)

		if current is not None and current < 9:
			arrSmartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["thermal_runaway"] = False
				arrSmartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arrSmartplugs_new)

		if current is not None and current < 10:
			arrSmartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["event_on_error"] = False
				plug["event_on_disconnect"] = False
				arrSmartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arrSmartplugs_new)

		if current is not None and current < 11:
			arrSmartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["automaticShutdownEnabled"] = False
				arrSmartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arrSmartplugs_new)

		if current is not None and current < 12:
			arrSmartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["event_on_upload"] = False
				arrSmartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arrSmartplugs_new)

		if current is not None and current < 13:
			arrSmartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["event_on_startup"] = False
				arrSmartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arrSmartplugs_new)

		if current is not None and current < 14:
			arrSmartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				if "/" in plug["ip"]:
					plug_ip, plug_num = plug["ip"].split("/")
					plug["ip"] = "{}/{}".format(plug_ip, int(plug_num) + 1)
				arrSmartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arrSmartplugs_new)

		if current is not None and current < 15:
			arrSmartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["gcodeCmdOn"] = False
				plug["gcodeCmdOff"] = False
				plug["gcodeRunCmdOn"] = ""
				plug["gcodeRunCmdOff"] = ""
				arrSmartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arrSmartplugs_new)

		if current is not None and current < 16:
			arrSmartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["event_on_shutdown"] = False
				arrSmartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"], arrSmartplugs_new)

	##~~ AssetPlugin mixin

	def get_assets(self):
		css = ["css/fontawesome-iconpicker.css",
			   "css/tplinksmartplug.css",
			   ]

		if not is_octoprint_compatible(">=1.5.0"):
			css += [
				"css/font-awesome.min.css",
				"css/font-awesome-v4-shims.min.css",
			]

		return {'js': ["js/jquery-ui.min.js",
					   "js/knockout-sortable.1.2.0.js",
					   "js/fontawesome-iconpicker.js",
					   "js/ko.iconpicker.js",
					   "js/tplinksmartplug.js",
					   "js/knockout-bootstrap.min.js",
					   "js/ko.observableDictionary.js",
					   "js/plotly-latest.min.js"],
				'css': css}

	##~~ TemplatePlugin mixin

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

	##~~ ProgressPlugin mixin

	def on_print_progress(self, storage, path, progress):
		if self._settings.get_boolean(["progress_polling"]) is False:
			return
		self._tplinksmartplug_logger.debug("Checking statuses during print progress (%s)." % progress)
		_print_progress_timer = threading.Timer(1, self.check_statuses)
		_print_progress_timer.daemon = True
		_print_progress_timer.start()
		self._plugin_manager.send_plugin_message(self._identifier, dict(updatePlot=True))

		if self.powerOffWhenIdle is True and not (self._skipIdleTimer is True):
			self._tplinksmartplug_logger.debug("Resetting idle timer during print progress (%s)..." % progress)
			self._waitForHeaters = False
			self._reset_idle_timer()

	##~~ SimpleApiPlugin mixin

	def turn_on(self, plugip):
		self._tplinksmartplug_logger.debug("Turning on %s." % plugip)
		plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
		self._tplinksmartplug_logger.debug(plug)
		if "/" in plugip:
			plug_ip, plug_num = plugip.split("/")
		else:
			plug_ip = plugip
			plug_num = 0
		if plug["useCountdownRules"] and int(plug["countdownOnDelay"]) > 0:
			self.sendCommand(json.loads('{"count_down":{"delete_all_rules":null}}'), plug_ip, plug_num)
			chk = self.lookup(self.sendCommand(json.loads(
				'{"count_down":{"add_rule":{"enable":1,"delay":%s,"act":1,"name":"turn on"}}}' % plug[
					"countdownOnDelay"]), plug_ip, plug_num), *["count_down", "add_rule", "err_code"])
			if chk == 0:
				self._countdown_active = True
				c = threading.Timer(int(plug["countdownOnDelay"]) + 3, self._plugin_manager.send_plugin_message,
									[self._identifier, dict(check_status=True, ip=plugip)])
				c.daemon = True
				c.start()
		else:
			turn_on_cmnd = dict(system=dict(set_relay_state=dict(state=1)))
			chk = self.lookup(self.sendCommand(turn_on_cmnd, plug_ip, plug_num),
							  *["system", "set_relay_state", "err_code"])

		self._tplinksmartplug_logger.debug(chk)
		if chk == 0:
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
				self._tplinksmartplug_logger.debug("Resetting idle timer since plug %s was just turned on." % plugip)
				self._waitForHeaters = False
				self._reset_idle_timer()

		return self.check_status(plugip)

	def turn_off(self, plugip):
		timenow = datetime.now()
		self._tplinksmartplug_logger.debug("Turning off %s." % plugip)
		self._tplinksmartplug_logger.info("Turning off %s at %s" % (plugip, timenow))
		plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
		self._tplinksmartplug_logger.debug(plug)
		if "/" in plugip:
			plug_ip, plug_num = plugip.split("/")
		else:
			plug_ip = plugip
			plug_num = 0
		if plug["useCountdownRules"] and int(plug["countdownOffDelay"]) > 0:
			self.sendCommand(json.loads('{"count_down":{"delete_all_rules":null}}'), plug_ip, plug_num)
			chk = self.lookup(self.sendCommand(json.loads(
				'{"count_down":{"add_rule":{"enable":1,"delay":%s,"act":0,"name":"turn off"}}}' % plug[
					"countdownOffDelay"]), plug_ip, plug_num), *["count_down", "add_rule", "err_code"])
			if chk == 0:
				self._countdown_active = True
				c = threading.Timer(int(plug["countdownOffDelay"]) + 3, self._plugin_manager.send_plugin_message,
									[self._identifier, dict(check_status=True, ip=plugip)])
				c.start()
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

		if not plug["useCountdownRules"]:
			turn_off_cmnd = dict(system=dict(set_relay_state=dict(state=0)))
			chk = self.lookup(self.sendCommand(turn_off_cmnd, plug_ip, plug_num),
							  *["system", "set_relay_state", "err_code"])

		self._tplinksmartplug_logger.debug(chk)

		return self.check_status(plugip)

	def check_statuses(self):
		for plug in self._settings.get(["arrSmartplugs"]):
			chk = self.check_status(plug["ip"])
			self._plugin_manager.send_plugin_message(self._identifier, chk)

	def check_status(self, plugip):
		self._tplinksmartplug_logger.debug("Checking status of %s." % plugip)
		if plugip != "":
			emeter_data = None
			today = datetime.today()
			check_status_cmnd = dict(system=dict(get_sysinfo=dict()))
			plug_ip = plugip.split("/")
			self._tplinksmartplug_logger.debug(check_status_cmnd)
			if len(plug_ip) == 2:
				response = self.sendCommand(check_status_cmnd, plug_ip[0], plug_ip[1])
				timer_chk = self.lookup(response, *["system", "get_sysinfo", "children"])[int(plug_ip[1]) - 1][
					"on_time"]
			else:
				response = self.sendCommand(check_status_cmnd, plug_ip[0])
				timer_chk = self.deep_get(response, ["system", "get_sysinfo", "on_time"], default=0)

			if timer_chk == 0 and self._countdown_active:
				self._tplinksmartplug_logger.debug("Clearing previously active countdown timer flag")
				self._countdown_active = False

			self._tplinksmartplug_logger.debug(
				self.deep_get(response, ["system", "get_sysinfo", "feature"], default=""))
			if "ENE" in self.deep_get(response, ["system", "get_sysinfo", "feature"], default=""):
				# if "ENE" in self.lookup(response, *["system","get_sysinfo","feature"]):
				emeter_data_cmnd = dict(emeter=dict(get_realtime=dict()))
				if len(plug_ip) == 2:
					check_emeter_data = self.sendCommand(emeter_data_cmnd, plug_ip[0], plug_ip[1])
				else:
					check_emeter_data = self.sendCommand(emeter_data_cmnd, plug_ip[0])
				if self.lookup(check_emeter_data, *["emeter", "get_realtime"]):
					emeter_data = check_emeter_data["emeter"]
					if "voltage_mv" in emeter_data["get_realtime"]:
						v = emeter_data["get_realtime"]["voltage_mv"] / 1000.0
					elif "voltage" in emeter_data["get_realtime"]:
						v = emeter_data["get_realtime"]["voltage"]
					else:
						v = ""
					if "current_ma" in emeter_data["get_realtime"]:
						c = emeter_data["get_realtime"]["current_ma"] / 1000.0
					elif "current" in emeter_data["get_realtime"]:
						c = emeter_data["get_realtime"]["current"]
					else:
						c = ""
					if "power_mw" in emeter_data["get_realtime"]:
						p = emeter_data["get_realtime"]["power_mw"] / 1000.0
					elif "power" in emeter_data["get_realtime"]:
						p = emeter_data["get_realtime"]["power"]
					else:
						p = ""
					if "total_wh" in emeter_data["get_realtime"]:
						t = emeter_data["get_realtime"]["total_wh"] / 1000.0
					elif "total" in emeter_data["get_realtime"]:
						t = emeter_data["get_realtime"]["total"]
					else:
						t = ""
					if self.db_path is not None:
						db = sqlite3.connect(self.db_path)
						cursor = db.cursor()
						cursor.execute(
							'''INSERT INTO energy_data(ip, timestamp, current, power, total, voltage) VALUES(?,?,?,?,?,?)''',
							[plugip, today.isoformat(' '), c, p, t, v])
						db.commit()
						db.close()

			if len(plug_ip) == 2:
				chk = self.lookup(response, *["system", "get_sysinfo", "children"])
				if chk:
					chk = chk[int(plug_ip[1]) - 1]["state"]
			else:
				chk = self.lookup(response, *["system", "get_sysinfo", "relay_state"])

			if chk == 1:
				return dict(currentState="on", emeter=emeter_data, ip=plugip)
			elif chk == 0:
				return dict(currentState="off", emeter=emeter_data, ip=plugip)
			else:
				self._tplinksmartplug_logger.debug(response)
				return dict(currentState="unknown", emeter=emeter_data, ip=plugip)

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
		self._tplinksmartplug_logger.debug(request.args)
		if request.args.get("checkStatus"):
			response = self.check_status(request.args.get("checkStatus"))
			return flask.jsonify(response)

	def on_api_command(self, command, data):
		if not Permissions.PLUGIN_TPLINKSMARTPLUG_CONTROL.can():
			return flask.make_response("Insufficient rights", 403)

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
				'''SELECT timestamp, current, power, total, voltage FROM energy_data WHERE ip=? ORDER BY timestamp DESC LIMIT ?,?''',
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
			for plug in self._settings.get(["arrSmartplugs"]):
				if plug["useCountdownRules"] and int(plug["countdownOffDelay"]) > 0:
					if "/" in plug["ip"]:
						plug_ip, plug_num = plug["ip"].split("/")
					else:
						plug_ip = plug["ip"]
						plug_num = 0
					self.sendCommand(json.loads('{"count_down":{"delete_all_rules":null}}'), plug_ip, plug_num)
					self._tplinksmartplug_logger.debug("Cleared countdown rules for %s" % plug["ip"])
			self._tplinksmartplug_logger.debug("Power off aborted.")
			self._tplinksmartplug_logger.debug("Restarting idle timer.")
			self._reset_idle_timer()
		elif command == "getListPlug":
			return json.dumps(self._settings.get(["arrSmartplugs"]))
		else:
			response = dict(ip="{ip}".format(**data), currentState="unknown")
		if command == "enableAutomaticShutdown" or command == "disableAutomaticShutdown":
			self._tplinksmartplug_logger.debug("Automatic power off setting changed: %s" % self.powerOffWhenIdle)
			self._settings.set_boolean(["powerOffWhenIdle"], self.powerOffWhenIdle)
			self._settings.save()
		# eventManager().fire(Events.SETTINGS_UPDATED)
		if command == "enableAutomaticShutdown" or command == "disableAutomaticShutdown" or command == "abortAutomaticShutdown":
			self._plugin_manager.send_plugin_message(self._identifier,
													 dict(powerOffWhenIdle=self.powerOffWhenIdle, type="timeout",
														  timeout_value=self._timeout_value))
		else:
			return flask.jsonify(response)

	##~~ EventHandlerPlugin mixin

	def on_event(self, event, payload):
		# Startup Event
		if event == Events.STARTUP and self._settings.get_boolean(["event_on_startup_monitoring"]) is True:
			self._tplinksmartplug_logger.debug("powering on due to %s event." % event)
			for plug in self._settings.get(['arrSmartplugs']):
				if plug["event_on_startup"] is True:
					self._tplinksmartplug_logger.debug("powering on %s due to %s event." % (plug["ip"], event))
					response = self.turn_on(plug["ip"])
					if response["currentState"] == "on":
						self._plugin_manager.send_plugin_message(self._identifier, response)
		# Error Event
		if event == Events.ERROR and self._settings.get_boolean(["event_on_error_monitoring"]) is True:
			self._tplinksmartplug_logger.debug("powering off due to %s event." % event)
			for plug in self._settings.get(['arrSmartplugs']):
				if plug["event_on_error"] is True:
					self._tplinksmartplug_logger.debug("powering off %s due to %s event." % (plug["ip"], event))
					response = self.turn_off(plug["ip"])
					if response["currentState"] == "off":
						self._plugin_manager.send_plugin_message(self._identifier, response)
		# Client Opened Event
		if event == Events.CLIENT_OPENED:
			if self._settings.get_boolean(["powerOffWhenIdle"]):
				self._tplinksmartplug_logger.debug("resetting idle timer due to %s event." % event)
				self._reset_idle_timer()
			self._plugin_manager.send_plugin_message(self._identifier,
													 dict(powerOffWhenIdle=self.powerOffWhenIdle, type="timeout",
														  timeout_value=self._timeout_value))
			return
		# Cancelled Print Interpreted Event
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

		if event == Events.PRINT_STARTED and self._countdown_active:
			for plug in self._settings.get(["arrSmartplugs"]):
				if plug["useCountdownRules"] and int(plug["countdownOffDelay"]) > 0:
					if "/" in plug["ip"]:
						plug_ip, plug_num = plug["ip"].split("/")
					else:
						plug_ip = plug["ip"]
						plug_num = 0
					self.sendCommand(json.loads('{"count_down":{"delete_all_rules":null}}'), plug_ip, plug_num)
					self._tplinksmartplug_logger.debug("Cleared countdown rules for %s" % plug["ip"])
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
			self._tplinksmartplug_logger.debug("hours: %s" % hours)
			power_used = self.print_job_power * hours
			self._tplinksmartplug_logger.debug("power used: %s" % power_used)
			power_cost = power_used * self._settings.get_float(["cost_rate"])
			self._tplinksmartplug_logger.debug("power total cost: %s" % power_cost)

			self._storage_interface = self._file_manager._storage(payload.get("origin", "local"))
			self._storage_interface.set_additional_metadata(payload.get("path"), "statistics", dict(
				lastPowerCost=dict(_default=float('{:.4f}'.format(power_cost)))), merge=True)

			self.print_job_power = 0.0
			self.print_job_started = False
			self._autostart_file = None

		if event == Events.PRINT_DONE and len(self.power_off_queue) > 0:
			self._tplinksmartplug_logger.debug("power_off_queue: {}".format(self.power_off_queue))
			for plug in self.power_off_queue:
				chk = self.turn_off(plug["ip"])
				self._plugin_manager.send_plugin_message(self._identifier, chk)
			self.power_off_queue = []

		if self.powerOffWhenIdle is True and event == Events.MOVIE_RENDERING:
			self._tplinksmartplug_logger.debug("Timelapse generation started: %s" % payload.get("movie_basename", ""))
			self._timelapse_active = True

		if self._timelapse_active and event == Events.MOVIE_DONE or event == Events.MOVIE_FAILED:
			self._tplinksmartplug_logger.debug("Timelapse generation finished: %s. Return Code: %s" % (
				payload.get("movie_basename", ""), payload.get("returncode", "completed")))
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
				self._tplinksmartplug_logger.debug("printer connected starting print of %s" % self._autostart_file)
				self._printer.select_file(self._autostart_file, False, printAfterSelect=True)
				self._autostart_file = None
		# File Uploaded Event
		if event == Events.UPLOAD and self._settings.get_boolean(["event_on_upload_monitoring"]):
			if payload.get("print", False) or self._settings.get_boolean(
					["event_on_upload_monitoring_always"]):  # implemented in OctoPrint version 1.4.1
				self._tplinksmartplug_logger.debug(
					"File uploaded: %s. Turning enabled plugs on." % payload.get("name", ""))
				self._tplinksmartplug_logger.debug(payload)
				for plug in self._settings.get(['arrSmartplugs']):
					self._tplinksmartplug_logger.debug(plug)
					if plug["event_on_upload"] is True and self._printer.is_closed_or_error():
						self._tplinksmartplug_logger.debug("powering on %s due to %s event." % (plug["ip"], event))
						response = self.turn_on(plug["ip"])
						if response["currentState"] == "on":
							self._tplinksmartplug_logger.debug(
								"power on successful for %s attempting connection in %s seconds" % (
									plug["ip"], plug.get("autoConnectDelay", "0")))
							self._plugin_manager.send_plugin_message(self._identifier, response)
							if payload.get("path", False) and payload.get("target") == "local":
								self._autostart_file = payload.get("path")
		# Shutdown Event
		if event == Events.SHUTDOWN and self._settings.get_boolean(["event_on_shutdown_monitoring"]):
			for plug in self._settings.get(['arrSmartplugs']):
				if plug["event_on_shutdown"] is True:
					self._tplinksmartplug_logger.debug("powering off %s due to shutdown event." % plug["ip"])
					self.turn_off(plug["ip"])

	##~~ Idle Timeout

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
		except:
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

	##~~ Timelapse Monitoring

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

	##~~ Temperature Cooldown

	def _wait_for_heaters(self):
		self._waitForHeaters = True
		heaters = self._printer.get_current_temperatures()

		for heater, entry in heaters.items():
			target = entry.get("target")
			if target is None:
				# heater doesn't exist in fw
				continue

			try:
				temp = float(target)
			except ValueError:
				# not a float for some reason, skip it
				continue

			if temp != 0:
				self._tplinksmartplug_logger.debug("Turning off heater: %s" % heater)
				self._skipIdleTimer = True
				self._printer.set_temperature(heater, 0)
				self._skipIdleTimer = False
			else:
				self._tplinksmartplug_logger.debug("Heater %s already off." % heater)

		while True:
			if not self._waitForHeaters:
				return False

			heaters = self._printer.get_current_temperatures()

			highest_temp = 0
			heaters_above_waittemp = []
			for heater, entry in heaters.items():
				if not heater.startswith("tool"):
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

				self._tplinksmartplug_logger.debug("Heater %s = %sC" % (heater, temp))
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

	##~~ Abort Power Off Timer

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

	##~~ Utilities

	def _get_device_id(self, plugip):
		response = self._settings.get([plugip])
		if not response:
			check_status_cmnd = dict(system=dict(get_sysinfo=dict()))
			plug_ip = plugip.split("/")
			self._tplinksmartplug_logger.debug(check_status_cmnd)
			plug_data = self.sendCommand(check_status_cmnd, plug_ip[0])
			if len(plug_ip) == 2:
				response = self.deep_get(plug_data, ["system", "get_sysinfo", "children"], default=False)
				if response:
					response = response[int(plug_ip[1]) - 1]["id"]
			else:
				response = self.deep_get(response, ["system", "get_sysinfo", "deviceId"])
			if response:
				self._settings.set([plugip], response)
				self._settings.save()
		self._tplinksmartplug_logger.debug("get_device_id response: %s" % response)
		return response

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

	def plug_search(self, list, key, value):
		for item in list:
			if item[key] == value.strip():
				return item

	def encrypt(self, string):
		key = 171
		result = b"\0\0\0" + bytes([len(string)])
		for i in bytes(string.encode('latin-1')):
			a = key ^ i
			key = a
			result += bytes([a])
		return result

	def decrypt(self, string):
		key = 171
		result = b""
		for i in bytes(string):
			a = key ^ i
			key = i
			result += bytes([a])
		return result.decode('latin-1')

	def sendCommand(self, cmd, plugip, plug_num=0):
		commands = {'info': '{"system":{"get_sysinfo":{}}}',
					'on': '{"system":{"set_relay_state":{"state":1}}}',
					'off': '{"system":{"set_relay_state":{"state":0}}}',
					'cloudinfo': '{"cnCloud":{"get_info":{}}}',
					'wlanscan': '{"netif":{"get_scaninfo":{"refresh":0}}}',
					'time': '{"time":{"get_time":{}}}',
					'schedule': '{"schedule":{"get_rules":{}}}',
					'countdown': '{"count_down":{"get_rules":{}}}',
					'antitheft': '{"anti_theft":{"get_rules":{}}}',
					'reboot': '{"system":{"reboot":{"delay":1}}}',
					'reset': '{"system":{"reset":{"delay":1}}}'
					}
		if re.search('/\d+$', plugip):
			self._tplinksmartplug_logger.exception("Internal error passing unsplit %s", plugip)
		# try to connect via ip address
		try:
			socket.inet_aton(plugip)
			ip = plugip
			self._tplinksmartplug_logger.debug("IP %s is valid." % plugip)
		except socket.error:
			# try to convert hostname to ip
			self._tplinksmartplug_logger.debug("Invalid ip %s trying hostname." % plugip)
			try:
				ip = socket.gethostbyname(plugip)
				self._tplinksmartplug_logger.debug("Hostname %s is valid." % plugip)
			except (socket.herror, socket.gaierror):
				self._tplinksmartplug_logger.debug("Invalid hostname %s." % plugip)
				return {"system": {"get_sysinfo": {"relay_state": 3}}, "emeter": {"err_code": True}}

		if int(plug_num) >= 1:
			plug_ip_num = "{}/{}".format(plugip, int(plug_num))
			cmd["context"] = dict(child_ids=[self._get_device_id(plug_ip_num)])

		try:
			self._tplinksmartplug_logger.debug("Sending command %s to %s" % (cmd, plugip))
			sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			sock_tcp.connect((ip, 9999))
			sock_tcp.send(self.encrypt(json.dumps(cmd)))
			data = sock_tcp.recv(1024)
			len_data = unpack('>I', data[0:4])
			while (len(data) - 4) < len_data[0]:
				data = data + sock_tcp.recv(1024)
			sock_tcp.close()

			self._tplinksmartplug_logger.debug(self.decrypt(data))
			return json.loads(self.decrypt(data[4:]))
		except socket.error:
			self._tplinksmartplug_logger.debug("Could not connect to %s." % plugip)
			return {"system": {"get_sysinfo": {"relay_state": 3}}, "emeter": {"err_code": True}}

	##~~ Gcode processing hook

	def gcode_turn_off(self, plug):
		if self._printer.is_printing() and plug["warnPrinting"] is True:
			self._tplinksmartplug_logger.debug(
				"Not powering off %s immediately because printer is printing." % plug["label"])
			self.power_off_queue.append(plug)
		else:
			chk = self.turn_off(plug["ip"])
			self._plugin_manager.send_plugin_message(self._identifier, chk)

	def gcode_turn_on(self, plug):
		chk = self.turn_on(plug["ip"])
		self._plugin_manager.send_plugin_message(self._identifier, chk)

	def processGCODE(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
		if self.powerOffWhenIdle and not (gcode in self._idleIgnoreCommandsArray):
			self._waitForHeaters = False
			self._reset_idle_timer()

		if gcode not in ["M80", "M81"]:
			return

		if gcode == "M80":
			plugip = re.sub(r'^M80\s?', '', cmd)
			self._tplinksmartplug_logger.debug("Received M80 command, attempting power on of %s." % plugip)
			plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
			self._tplinksmartplug_logger.debug(plug)
			if plug and plug["gcodeEnabled"]:
				t = threading.Timer(int(plug["gcodeOnDelay"]), self.gcode_turn_on, [plug])
				t.daemon = True
				t.start()
			return
		if gcode == "M81":
			plugip = re.sub(r'^M81\s?', '', cmd)
			self._tplinksmartplug_logger.debug("Received M81 command, attempting power off of %s." % plugip)
			plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
			self._tplinksmartplug_logger.debug(plug)
			if plug and plug["gcodeEnabled"]:
				t = threading.Timer(int(plug["gcodeOffDelay"]), self.gcode_turn_off, [plug])
				t.daemon = True
				t.start()
			return

	def processAtCommand(self, comm_instance, phase, command, parameters, tags=None, *args, **kwargs):
		if command == "TPLINKON":
			plugip = parameters
			self._tplinksmartplug_logger.debug("Received TPLINKON command, attempting power on of %s." % plugip)
			plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
			self._tplinksmartplug_logger.debug(plug)
			if plug and plug["gcodeEnabled"]:
				t = threading.Timer(int(plug["gcodeOnDelay"]), self.gcode_turn_on, [plug])
				t.daemon = True
				t.start()
			return None
		if command == "TPLINKOFF":
			plugip = parameters
			self._tplinksmartplug_logger.debug("Received TPLINKOFF command, attempting power off of %s." % plugip)
			plug = self.plug_search(self._settings.get(["arrSmartplugs"]), "ip", plugip)
			self._tplinksmartplug_logger.debug(plug)
			if plug and plug["gcodeEnabled"]:
				t = threading.Timer(int(plug["gcodeOffDelay"]), self.gcode_turn_off, [plug])
				t.daemon = True
				t.start()
			return None
		if command == 'TPLINKIDLEON':
			self.powerOffWhenIdle = True
			self._reset_idle_timer()
		if command == 'TPLINKIDLEOFF':
			self.powerOffWhenIdle = False
			self._stop_idle_timer()
			if self._abort_timer is not None:
				self._abort_timer.cancel()
				self._abort_timer = None
			self._timeout_value = None
		if command in ["TPLINKIDLEON", "TPLINKIDLEOFF"]:
			self._plugin_manager.send_plugin_message(self._identifier,
													 dict(powerOffWhenIdle=self.powerOffWhenIdle, type="timeout",
														  timeout_value=self._timeout_value))

	##~~ Temperatures received hook

	def check_temps(self, parsed_temps):
		thermal_runaway_triggered = False
		for k, v in list(parsed_temps.items()):
			if k == "B" and v[0] > int(self._settings.get(["thermal_runaway_max_bed"])):
				self._tplinksmartplug_logger.debug("Max bed temp reached, shutting off plugs.")
				thermal_runaway_triggered = True
			if k.startswith("T") and v[0] > int(self._settings.get(["thermal_runaway_max_extruder"])):
				self._tplinksmartplug_logger.debug("Extruder max temp reached, shutting off plugs.")
				thermal_runaway_triggered = True
			if thermal_runaway_triggered == True:
				for plug in self._settings.get(['arrSmartplugs']):
					if plug["thermal_runaway"] == True:
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

	##~~ Access Permissions Hook

	def get_additional_permissions(self, *args, **kwargs):
		return [
			dict(key="CONTROL",
				 name="Control Plugs",
				 description=gettext("Allows control of configured plugs."),
				 roles=["admin"],
				 dangerous=True,
				 default_groups=[ADMIN_GROUP])
		]

	##~~ Softwareupdate hook

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
		"octoprint.comm.protocol.gcode.queuing": __plugin_implementation__.processGCODE,
		"octoprint.comm.protocol.atcommand.sending": __plugin_implementation__.processAtCommand,
		"octoprint.comm.protocol.temperatures.received": __plugin_implementation__.monitor_temperatures,
		"octoprint.access.permissions": __plugin_implementation__.get_additional_permissions,
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}
