# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.server import user_permission
import socket
import json
import time
import logging
import os
import re

class tplinksmartplugPlugin(octoprint.plugin.SettingsPlugin,
                            octoprint.plugin.AssetPlugin,
                            octoprint.plugin.TemplatePlugin,
							octoprint.plugin.SimpleApiPlugin,
							octoprint.plugin.StartupPlugin):
							
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
	
	def on_after_startup(self):
		self._logger.info("TPLinkSmartplug loaded!")
	
	##~~ SettingsPlugin mixin
	
	def get_settings_defaults(self):
		return dict(
			debug_logging = False,
			arrSmartplugs = [{'ip':'','displayWarning':True,'warnPrinting':False,'gcodeEnabled':False,'gcodeOnDelay':0,'gcodeOffDelay':0,'autoConnect':True,'autoConnectDelay':10.0,'autoDisconnect':True,'autoDisconnectDelay':0,'sysCmdOn':False,'sysRunCmdOn':'','sysCmdOnDelay':0,'sysCmdOff':False,'sysRunCmdOff':'','sysCmdOffDelay':0,'currentState':'unknown','btnColor':'#808080'}],
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
		return 3
		
	def on_settings_migrate(self, target, current=None):
		if current is None or current < self.get_settings_version():
			# Reset plug settings to defaults.
			self._logger.debug("Resetting arrSmartplugs for tplinksmartplug settings.")
			self._settings.set(['arrSmartplugs'], self.get_settings_defaults()["arrSmartplugs"])
		
	##~~ AssetPlugin mixin

	def get_assets(self):
		return dict(
			js=["js/tplinksmartplug.js"]
		)
		
	##~~ TemplatePlugin mixin
	
	def get_template_configs(self):
		return [
			dict(type="navbar", custom_bindings=True),
			dict(type="settings", custom_bindings=True)
		]
		
	##~~ SimpleApiPlugin mixin
	
	def turn_on(self, plugip):
		self._tplinksmartplug_logger.debug("Turning on %s." % plugip)
		chk = self.sendCommand("on",plugip)["system"]["set_relay_state"]["err_code"]
		if chk == 0:
			self.check_status(plugip)
	
	def turn_off(self, plugip):
		self._tplinksmartplug_logger.debug("Turning off %s." % plugip)
		chk = self.sendCommand("off",plugip)["system"]["set_relay_state"]["err_code"]
		if chk == 0:
			self.check_status(plugip)
		
	def check_status(self, plugip):
		self._tplinksmartplug_logger.debug("Checking status of %s." % plugip)
		if plugip != "":
			response = self.sendCommand("info",plugip)
			chk = response["system"]["get_sysinfo"]["relay_state"]
			if chk == 1:
				self._plugin_manager.send_plugin_message(self._identifier, dict(currentState="on",ip=plugip))
			elif chk == 0:
				self._plugin_manager.send_plugin_message(self._identifier, dict(currentState="off",ip=plugip))
			else:
				self._tplinksmartplug_logger.debug(response)
				self._plugin_manager.send_plugin_message(self._identifier, dict(currentState="unknown",ip=plugip))		
	
	def get_api_commands(self):
		return dict(turnOn=["ip"],turnOff=["ip"],checkStatus=["ip"],connectPrinter=[],disconnectPrinter=[],sysCommand=["cmd"])

	def on_api_command(self, command, data):
		if not user_permission.can():
			from flask import make_response
			return make_response("Insufficient rights", 403)
        
		if command == 'turnOn':
			self.turn_on("{ip}".format(**data))
		elif command == 'turnOff':
			self.turn_off("{ip}".format(**data))
		elif command == 'checkStatus':
			self.check_status("{ip}".format(**data))
		elif command == 'connectPrinter':
			self._tplinksmartplug_logger.debug("Connecting printer.")
			self._printer.connect()
		elif command == 'disconnectPrinter':
			self._tplinksmartplug_logger.debug("Disconnecting printer.")
			self._printer.disconnect()
		elif command == 'sysCommand':
			self._tplinksmartplug_logger.debug("Running system command %s." % "{cmd}".format(**data))
			os.system("{cmd}".format(**data))
			
	##~~ Utilities
	
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
	
	def sendCommand(self, cmd, plugip):	
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
				return {"system":{"get_sysinfo":{"relay_state":3}}}
				
		try:
			sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			sock_tcp.connect((ip, 9999))
			sock_tcp.send(self.encrypt(commands[cmd]))
			data = sock_tcp.recv(2048)
			sock_tcp.close()
			
			self._tplinksmartplug_logger.debug("Sending command %s to %s" % (cmd,plugip))
			self._tplinksmartplug_logger.debug(self.decrypt(data))
			return json.loads(self.decrypt(data[4:]))
		except socket.error:
			self._tplinksmartplug_logger.debug("Could not connect to %s." % plugip)
			return {"system":{"get_sysinfo":{"relay_state":3}}}
			
	##~~ Gcode processing hook
	
	def processGCODE(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
		if gcode:
			if cmd.startswith("M80"):
				plugip = re.sub(r'^M80\s?', '', cmd)
				self._plugin_manager.send_plugin_message(self._identifier, dict(currentState="unknown",gcodeon=True,ip=plugip))
				self._tplinksmartplug_logger.debug("Received M80 command, attempting power on.")
				return
			elif cmd.startswith("M81"):
				plugip = re.sub(r'^M81\s?', '', cmd)
				self._plugin_manager.send_plugin_message(self._identifier, dict(currentState="unknown",gcodeoff=True,ip=plugip))
				self._tplinksmartplug_logger.debug("Received M81 command, attempting power off.")
				return
			else:
				return
			

	##~~ Softwareupdate hook

	def get_update_information(self):
		# Define the configuration for your plugin to use with the Software Update
		# Plugin here. See https://github.com/foosel/OctoPrint/wiki/Plugin:-Software-Update
		# for details.
		return dict(
			tplinksmartplug=dict(
				displayName="TP-Link Smartplug",
				displayVersion=self._plugin_version,

				# version check: github repository
				type="github_release",
				user="jneilliii",
				repo="OctoPrint-TPLinkSmartplug",
				current=self._plugin_version,

				# update method: pip
				pip="https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/archive/{target_version}.zip"
			)
		)


# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "TP-Link Smartplug"

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = tplinksmartplugPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.comm.protocol.gcode.queuing": __plugin_implementation__.processGCODE,
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}

