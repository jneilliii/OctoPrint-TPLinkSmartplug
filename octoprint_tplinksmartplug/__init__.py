# coding=utf-8
from __future__ import absolute_import

import octoprint.plugin
from octoprint.server import user_permission
import socket
import JSON

class tplinksmartplugPlugin(octoprint.plugin.SettingsPlugin,
                            octoprint.plugin.AssetPlugin,
                            octoprint.plugin.TemplatePlugin,
							octoprint.plugin.SimpleApiPlugin):
							
	def on_after_startup(self):
		self._logger.info("TPLinkSmartplug started.")

	##~~ SettingsPlugin mixin

	def get_settings_defaults(self):
		return dict(
			currentState = "unknown",
            ip = '',
            postOnDelay = 0.0,
            disconnectOnPowerOff = False,
            connectOnPowerOn = False,
            connectOnPowerOnDelay = 0.0
		)

	##~~ AssetPlugin mixin

	def get_assets(self):
		return dict(
			js=["js/tplinksmartplug.js"],
			css=["css/tplinksmartplug.css"]
		)
		
	##~~ TemplatePlugin mixin
	
	def get_template_configs(self):
		return [
			dict(type="navbar", custom_bindings=True),
			dict(type="settings", custom_bindings=True)
		]
		
	##~~ SimpleApiPlugin mixin
	
	def turn_on(self):
		self._logger.info("Turning on.")
		self._plugin_manager.send_plugin_message(self._identifier, dict(currentState="on"))
	
	def turn_off(self):
		self._logger.info("Turning off.")
		self._plugin_manager.send_plugin_message(self._identifier, dict(currentState="off"))
		
	def check_status(self):
		self.logger.info("Checking status.")
		self.logger.info(self.sendCommand('{"system":{"get_sysinfo":{}}}')["system"]["get_sysinfo"]["relay_state"])
		self._plugin_manager.send_plugin_message(self._identifier, dict(currentState="unknown"))
	
	def get_api_commands(self):
		return dict(turnOn=[],turnOff=[],checkStatus=[])

	def on_api_command(self, command, data):
		if not user_permission.can():
			return make_response("Insufficient rights", 403)
        
		if command == 'turnOn':
			self.turn_on()
		elif command == 'turnOff':
			self.turn_off()
		elif command == 'checkStatus':
			self.check_status()
			
	##~~ Utilities
	
	def encrypt(string):
		key = 171
		result = "\0\0\0\0"
		for i in string: 
			a = key ^ ord(i)
			key = a
			result += chr(a)
		return result

	def decrypt(string):
		key = 171 
		result = ""
		for i in string: 
			a = key ^ ord(i)
			key = ord(i) 
			result += chr(a)
		return result
	
	def sendCommand(cmd):
		try:
			sock_tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			sock_tcp.connect((self._settings.plugins.tplinksmartplug.ip, 9999))
			sock_tcp.send(encrypt(cmd))
			data = sock_tcp.recv(2048)
			sock_tcp.close()
			
			self._logger.info("Sending command %s" % cmd)
			return JSON.loads(decrypt(data[4:]))
		except socket.error:
			self._logger.info("Error sending command")

	##~~ Softwareupdate hook

	def get_update_information(self):
		# Define the configuration for your plugin to use with the Software Update
		# Plugin here. See https://github.com/foosel/OctoPrint/wiki/Plugin:-Software-Update
		# for details.
		return dict(
			tplinksmartplug=dict(
				displayName="TPLink Smartplug Control",
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
__plugin_name__ = "TPLinkSmartplug Plugin"

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = tplinksmartplugPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}

