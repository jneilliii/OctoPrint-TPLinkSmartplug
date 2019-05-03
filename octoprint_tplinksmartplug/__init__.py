# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.server import user_permission
import socket
import json
import flask
import logging
import os
import re
import threading
import time
import sqlite3
from datetime import datetime
from struct import unpack

class tplinksmartplugPlugin(octoprint.plugin.SettingsPlugin,
							octoprint.plugin.AssetPlugin,
							octoprint.plugin.TemplatePlugin,
							octoprint.plugin.SimpleApiPlugin,
							octoprint.plugin.StartupPlugin,
							octoprint.plugin.ProgressPlugin):

	def __init__(self):
		self._logger = logging.getLogger("octoprint.plugins.tplinksmartplug")
		self._tplinksmartplug_logger = logging.getLogger("octoprint.plugins.tplinksmartplug.debug")

	##~~ StartupPlugin mixin

	def on_startup(self, host, port):
		# setup customized logger
		from octoprint.logging.handlers import CleaningTimedRotatingFileHandler
		tplinksmartplug_logging_handler = CleaningTimedRotatingFileHandler(self._settings.get_plugin_logfile_path(postfix="debug"), when="D", backupCount=3)
		tplinksmartplug_logging_handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
		tplinksmartplug_logging_handler.setLevel(logging.DEBUG)

		self._tplinksmartplug_logger.addHandler(tplinksmartplug_logging_handler)
		self._tplinksmartplug_logger.setLevel(logging.DEBUG if self._settings.get_boolean(["debug_logging"]) else logging.INFO)
		self._tplinksmartplug_logger.propagate = False

		self.db_path = os.path.join(self.get_plugin_data_folder(),"energy_data.db")
		if not os.path.exists(self.db_path):
			self.db = sqlite3.connect(self.db_path)
			cursor = self.db.cursor()
			cursor.execute('''CREATE TABLE energy_data(id INTEGER PRIMARY KEY, ip TEXT, timestamp TEXT, current REAL, power REAL, total REAL, voltage REAL)''')
			self.db.commit()
			self.db.close()

	def on_after_startup(self):
		self._logger.info("TPLinkSmartplug loaded!")

	##~~ SettingsPlugin mixin

	def get_settings_defaults(self):
		return dict(
			debug_logging = False,
			arrSmartplugs = [{'ip':'','label':'','icon':'icon-bolt','displayWarning':True,'warnPrinting':False,'thermal_runaway':False,'gcodeEnabled':False,'gcodeOnDelay':0,'gcodeOffDelay':0,'autoConnect':True,'autoConnectDelay':10.0,'autoDisconnect':True,'autoDisconnectDelay':0,'sysCmdOn':False,'sysRunCmdOn':'','sysCmdOnDelay':0,'sysCmdOff':False,'sysRunCmdOff':'','sysCmdOffDelay':0,'currentState':'unknown','btnColor':'#808080','useCountdownRules':False,'countdownOnDelay':0,'countdownOffDelay':0,'emeter':{'get_realtime':{}}}],
			pollingInterval = 15,
			pollingEnabled = False,
			thermal_runaway_monitoring = False,
			thermal_runaway_max_bed = 0,
			thermal_runaway_max_extruder = 0
		)

	def on_settings_save(self, data):
		old_debug_logging = self._settings.get_boolean(["debug_logging"])

		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

		new_debug_logging = self._settings.get_boolean(["debug_logging"])
		if old_debug_logging != new_debug_logging:
			if new_debug_logging:
				self._tplinksmartplug_logger.setLevel(logging.DEBUG)
			else:
				self._tplinksmartplug_logger.setLevel(logging.INFO)

	def get_settings_version(self):
		return 9

	def on_settings_migrate(self, target, current=None):
		if current is None or current < 5:
			# Reset plug settings to defaults.
			self._logger.debug("Resetting arrSmartplugs for tplinksmartplug settings.")
			self._settings.set(['arrSmartplugs'], self.get_settings_defaults()["arrSmartplugs"])
		elif current == 6:
			# Loop through plug array and set emeter to None
			arrSmartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["emeter"] = None
				arrSmartplugs_new.append(plug)

			self._logger.info("Updating plug array, converting")
			self._logger.info(self._settings.get(['arrSmartplugs']))
			self._logger.info("to")
			self._logger.info(arrSmartplugs_new)
			self._settings.set(["arrSmartplugs"],arrSmartplugs_new)
		elif current == 7:
			# Loop through plug array and set emeter to None
			arrSmartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["emeter"] = dict(get_realtime = False)
				arrSmartplugs_new.append(plug)

			self._logger.info("Updating plug array, converting")
			self._logger.info(self._settings.get(['arrSmartplugs']))
			self._logger.info("to")
			self._logger.info(arrSmartplugs_new)
			self._settings.set(["arrSmartplugs"],arrSmartplugs_new)

		if current is not None and current < 9:
			arrSmartplugs_new = []
			for plug in self._settings.get(['arrSmartplugs']):
				plug["thermal_runaway"] = False
				arrSmartplugs_new.append(plug)
			self._settings.set(["arrSmartplugs"],arrSmartplugs_new)

	##~~ AssetPlugin mixin

	def get_assets(self):
		return dict(
			js=["js/tplinksmartplug.js","js/knockout-bootstrap.min.js","js/ko.observableDictionary.js","js/plotly-latest.min.js"],
			css=["css/tplinksmartplug.css"]
		)

	##~~ TemplatePlugin mixin

	def get_template_configs(self):
		templates_to_load = [dict(type="navbar", custom_bindings=True),dict(type="settings", custom_bindings=True),dict(type="sidebar", icon="plug", custom_bindings=True, data_bind="visible: show_sidebar()"),dict(type="tab", custom_bindings=True)]
		return templates_to_load

	def on_print_progress(self, storage, path, progress):
		self._tplinksmartplug_logger.debug("Checking statuses during print progress (%s)." % progress)
		for plug in self._settings.get(["arrSmartplugs"]):
			if plug["emeter"] and plug["emeter"] != {}:
				self.check_status(plug["ip"])

	##~~ SimpleApiPlugin mixin

	def turn_on(self, plugip):
		self._tplinksmartplug_logger.debug("Turning on %s." % plugip)
		plug = self.plug_search(self._settings.get(["arrSmartplugs"]),"ip",plugip)
		self._tplinksmartplug_logger.debug(plug)
		if plug["useCountdownRules"]:
			self.sendCommand(json.loads('{"count_down":{"delete_all_rules":null}}'),plug["ip"])
			chk = self.lookup(self.sendCommand(json.loads('{"count_down":{"add_rule":{"enable":1,"delay":%s,"act":1,"name":"turn on"}}}' % plug["countdownOnDelay"]),plug["ip"]),*["count_down","add_rule","err_code"])
		else:
			turn_on_cmnd = dict(system=dict(set_relay_state=dict(state=1)))
			plug_ip = plugip.split("/")
			if len(plug_ip) == 2:
				chk = self.lookup(self.sendCommand(turn_on_cmnd,plug_ip[0],plug_ip[1]),*["system","set_relay_state","err_code"])
			else:
				chk = self.lookup(self.sendCommand(turn_on_cmnd,plug_ip[0]),*["system","set_relay_state","err_code"])

		self._tplinksmartplug_logger.debug(chk)
		if chk == 0:
			if plug["autoConnect"]:
				c = threading.Timer(int(plug["autoConnectDelay"]),self._printer.connect)
				c.start()
			if plug["sysCmdOn"]:
				t = threading.Timer(int(plug["sysCmdOnDelay"]),os.system,args=[plug["sysRunCmdOn"]])
				t.start()
			return self.check_status(plugip)

	def turn_off(self, plugip):
		self._tplinksmartplug_logger.debug("Turning off %s." % plugip)
		plug = self.plug_search(self._settings.get(["arrSmartplugs"]),"ip",plugip)
		self._tplinksmartplug_logger.debug(plug)
		if plug["useCountdownRules"]:
			self.sendCommand(json.loads('{"count_down":{"delete_all_rules":null}}'),plug["ip"])
			chk = self.lookup(self.sendCommand(json.loads('{"count_down":{"add_rule":{"enable":1,"delay":%s,"act":0,"name":"turn off"}}}' % plug["countdownOffDelay"]),plug["ip"]),*["count_down","add_rule","err_code"])

		if plug["sysCmdOff"]:
			t = threading.Timer(int(plug["sysCmdOffDelay"]),os.system,args=[plug["sysRunCmdOff"]])
			t.start()
		if plug["autoDisconnect"]:
			self._printer.disconnect()
			time.sleep(int(plug["autoDisconnectDelay"]))

		if not plug["useCountdownRules"]:
			turn_off_cmnd = dict(system=dict(set_relay_state=dict(state=0)))
			plug_ip = plugip.split("/")
			if len(plug_ip) == 2:
				chk = self.lookup(self.sendCommand(turn_off_cmnd,plug_ip[0],plug_ip[1]),*["system","set_relay_state","err_code"])
			else:
				chk = self.lookup(self.sendCommand(turn_off_cmnd,plug_ip[0]),*["system","set_relay_state","err_code"])

		self._tplinksmartplug_logger.debug(chk)
		if chk == 0:
			return self.check_status(plugip)

	def check_status(self, plugip):
		self._tplinksmartplug_logger.debug("Checking status of %s." % plugip)
		if plugip != "":
			emeter_data = None
			today = datetime.today()
			check_status_cmnd = dict(system = dict(get_sysinfo = dict()))
			plug_ip = plugip.split("/")
			self._tplinksmartplug_logger.debug(check_status_cmnd)
			if len(plug_ip) == 2:
				response = self.sendCommand(check_status_cmnd, plug_ip[0], plug_ip[1])
			else:
				response = self.sendCommand(check_status_cmnd, plug_ip[0])

			if "ENE" in self.lookup(response, *["system","get_sysinfo","feature"]):
				emeter_data_cmnd = dict(emeter = dict(get_realtime = dict()))
				if len(plug_ip) == 2:
					check_emeter_data = self.sendCommand(emeter_data_cmnd, plug_ip[0], plug_ip[1])
				else:
					check_emeter_data = self.sendCommand(emeter_data_cmnd, plug_ip[0])
				if self.lookup(check_emeter_data, *["emeter","get_realtime"]):
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
					self.db = sqlite3.connect(self.db_path)
					cursor = self.db.cursor()
					cursor.execute('''INSERT INTO energy_data(ip, timestamp, current, power, total, voltage) VALUES(?,?,?,?,?,?)''', [plugip,today.isoformat(' '),c,p,t,v])
					self.db.commit()
					self.db.close()

			if len(plug_ip) == 2:
				chk = self.lookup(response,*["system","get_sysinfo","children"])
				if chk:
					chk = chk[int(plug_ip[1])]["state"]
			else:
				chk = self.lookup(response,*["system","get_sysinfo","relay_state"])

			if chk == 1:
				return dict(currentState="on",emeter=emeter_data,ip=plugip)
			elif chk == 0:
				return dict(currentState="off",emeter=emeter_data,ip=plugip)
			else:
				self._tplinksmartplug_logger.debug(response)
				return dict(currentState="unknown",emeter=emeter_data,ip=plugip)

	def get_api_commands(self):
		return dict(turnOn=["ip"],turnOff=["ip"],checkStatus=["ip"],getEnergyData=["ip"])

	def on_api_get(self, request):
		self._logger.info(request.args)
		if request.args.get("checkStatus"):
			response = self.check_status(request.args.get("checkStatus"))
			return flask.jsonify(response)

	def on_api_command(self, command, data):
		if not user_permission.can():
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
			self.db = sqlite3.connect(self.db_path)
			cursor = self.db.cursor()
			cursor.execute('''SELECT timestamp, current, power, total, voltage FROM energy_data WHERE ip=? ORDER BY timestamp DESC LIMIT ?,?''', (data["ip"],data["record_offset"],data["record_limit"],))
			response = {'energy_data' : cursor.fetchall()}
			self.db.close()
			self._logger.info(response)
			#SELECT * FROM energy_data WHERE ip = '192.168.0.102' LIMIT 0,30 
		else:
			response = dict(ip = data.ip, currentState = "unknown")
		return flask.jsonify(response)

	##~~ Utilities

	def _get_device_id(self, plugip):
		response = self._settings.get([plugip])
		if not response:
			check_status_cmnd = dict(system = dict(get_sysinfo = dict()))
			plug_ip = plugip.split("/")
			self._tplinksmartplug_logger.debug(check_status_cmnd)
			plug_data = self.sendCommand(check_status_cmnd, plug_ip[0])
			if len(plug_ip) == 2:
				response = self.deep_get(plug_data,["system","get_sysinfo","children"], default=False)
				if response:
					response = response[int(plug_ip[1])]["id"]
				self._tplinksmartplug_logger.debug(response)
			else:
				response = self.deep_get(response,["system","get_sysinfo","deviceId"])
			if response:
				self._settings.set([plugip],response)
				self._settings.save()
		return response

	def deep_get(self, d, keys, default=None):
		"""
		Example:
			d = {'meta': {'status': 'OK', 'status_code': 200}}
			deep_get(d, ['meta', 'status_code'])          # => 200
			deep_get(d, ['garbage', 'status_code'])       # => None
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
			if item[key] == value: 
				return item

	def encrypt(self, string):
		key = 171
		result = "\0\0\0"+chr(len(string))
		for i in string: 
			a = key ^ ord(i)
			key = a
			result += chr(a)
		return result

	def decrypt(self, string):
		key = 171 
		result = ""
		for i in string: 
			a = key ^ ord(i)
			key = ord(i) 
			result += chr(a)
		return result

	def sendCommand(self, cmd, plugip, plug_num = -1):
		commands = {'info'     : '{"system":{"get_sysinfo":{}}}',
			'on'       : '{"system":{"set_relay_state":{"state":1}}}',
			'off'      : '{"system":{"set_relay_state":{"state":0}}}',
			'cloudinfo': '{"cnCloud":{"get_info":{}}}',
			'wlanscan' : '{"netif":{"get_scaninfo":{"refresh":0}}}',
			'time'     : '{"time":{"get_time":{}}}',
			'schedule' : '{"schedule":{"get_rules":{}}}',
			'countdown': '{"count_down":{"get_rules":{}}}',
			'antitheft': '{"anti_theft":{"get_rules":{}}}',
			'reboot'   : '{"system":{"reboot":{"delay":1}}}',
			'reset'    : '{"system":{"reset":{"delay":1}}}'
		}

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
				return {"system":{"get_sysinfo":{"relay_state":3}},"emeter":{"err_code": True}}

		if plug_num >= 0:
			plug_ip_num = plugip + "/" + plug_num
			cmd["context"] = dict(child_ids = [self._get_device_id(plug_ip_num)])

		try:
			self._tplinksmartplug_logger.debug("Sending command %s to %s" % (cmd,plugip))
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
			return {"system":{"get_sysinfo":{"relay_state":3}},"emeter":{"err_code": True}}

	##~~ Gcode processing hook

	def gcode_turn_off(self, plug):
		if plug["warnPrinting"] and self._printer.is_printing():
			self._logger.info("Not powering off %s because printer is printing." % plug["label"])
		else:
			chk = self.turn_off(plug["ip"])
			self._plugin_manager.send_plugin_message(self._identifier, chk)

	def gcode_turn_on(self, plug):
		chk = self.turn_on(plug["ip"])
		self._plugin_manager.send_plugin_message(self._identifier, chk)

	def processGCODE(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
		if gcode:
			if cmd.startswith("M80"):
				plugip = re.sub(r'^M80\s?', '', cmd)
				self._tplinksmartplug_logger.debug("Received M80 command, attempting power on of %s." % plugip)
				plug = self.plug_search(self._settings.get(["arrSmartplugs"]),"ip",plugip)
				self._tplinksmartplug_logger.debug(plug)
				if plug["gcodeEnabled"]:
					t = threading.Timer(int(plug["gcodeOnDelay"]),self.gcode_turn_on,[plug])
					t.start()
				return
			elif cmd.startswith("M81"):
				plugip = re.sub(r'^M81\s?', '', cmd)
				self._tplinksmartplug_logger.debug("Received M81 command, attempting power off of %s." % plugip)
				plug = self.plug_search(self._settings.get(["arrSmartplugs"]),"ip",plugip)
				self._tplinksmartplug_logger.debug(plug)
				if plug["gcodeEnabled"]:
					t = threading.Timer(int(plug["gcodeOffDelay"]),self.gcode_turn_off,[plug])
					t.start()
				return
			else:
				return

		elif cmd.startswith("@TPLINKON"):
			plugip = re.sub(r'^@TPLINKON\s?', '', cmd)
			self._tplinksmartplug_logger.debug("Received @TPLINKON command, attempting power on of %s." % plugip)
			plug = self.plug_search(self._settings.get(["arrSmartplugs"]),"ip",plugip)
			self._tplinksmartplug_logger.debug(plug)
			if plug["gcodeEnabled"]:
				t = threading.Timer(int(plug["gcodeOnDelay"]),self.gcode_turn_on,[plug])
				t.start()
			return None
		elif cmd.startswith("@TPLINKOFF"):
			plugip = re.sub(r'^@TPLINKOFF\s?', '', cmd)
			self._tplinksmartplug_logger.debug("Received TPLINKOFF command, attempting power off of %s." % plugip)
			plug = self.plug_search(self._settings.get(["arrSmartplugs"]),"ip",plugip)
			self._tplinksmartplug_logger.debug(plug)
			if plug["gcodeEnabled"]:
				t = threading.Timer(int(plug["gcodeOffDelay"]),self.gcode_turn_off,[plug])
				t.start()
			return None

	##~~ Temperatures received hook

	def check_temps(self, parsed_temps):
		thermal_runaway_triggered = False
		for k, v in parsed_temps.items():
			if k == "B" and v[1] > 0 and v[0] > int(self._settings.get(["thermal_runaway_max_bed"])):
				self._tplinksmartplug_logger.debug("Max bed temp reached, shutting off plugs.")
				thermal_runaway_triggered = True
			if k.startswith("T") and v[1] > 0 and v[0] > int(self._settings.get(["thermal_runaway_max_extruder"])):
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
			t = threading.Timer(0,self.check_temps,[parsed_temps])
			t.start()
		return parsed_temps

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
				pip="https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/archive/{target_version}.zip"
			)
		)

__plugin_name__ = "TP-Link Smartplug"

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = tplinksmartplugPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.comm.protocol.gcode.queuing": __plugin_implementation__.processGCODE,
		"octoprint.comm.protocol.temperatures.received": __plugin_implementation__.monitor_temperatures,
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}

