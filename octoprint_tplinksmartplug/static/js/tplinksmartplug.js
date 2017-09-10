/*
 * View model for OctoPrint-TPLinkSmartplug
 *
 * Author: jneilliii
 * License: AGPLv3
 */
$(function() {
    function tplinksmartplugViewModel(parameters) {
        var self = this;

        self.settings = parameters[0];
		self.loginState = parameters[1];
		
		self.currentState = ko.observable("unknown");
		self.ip = ko.observable();
		self.relayState = ko.observable("#808080");
		self.disconnectOnPowerOff = ko.observable();
		self.connectOnPowerOn = ko.observable();
		self.connectOnPowerOnDelay = ko.observable();
		self.enablePowerOffWarningDialog = ko.observable();
		self.gcodeprocessing = ko.observable();
		
		self.onBeforeBinding = function() {
			self.ip(self.settings.settings.plugins.tplinksmartplug.ip());
			self.disconnectOnPowerOff(self.settings.settings.plugins.tplinksmartplug.disconnectOnPowerOff());
			self.connectOnPowerOn(self.settings.settings.plugins.tplinksmartplug.connectOnPowerOn());
			self.connectOnPowerOnDelay(self.settings.settings.plugins.tplinksmartplug.connectOnPowerOnDelay());
			self.enablePowerOffWarningDialog(self.settings.settings.plugins.tplinksmartplug.enablePowerOffWarningDialog());
			self.gcodeprocessing(self.settings.settings.plugins.tplinksmartplug.gcodeprocessing());
        }
		
		self.onAfterBinding = function() {
			self.checkStatus();
			self.poweroff_dialog = $("#tplinksmartplug_poweroff_confirmation_dialog");
		}

        self.onEventSettingsUpdated = function (payload) {
			self.ip(self.settings.settings.plugins.tplinksmartplug.ip());
			self.disconnectOnPowerOff(self.settings.settings.plugins.tplinksmartplug.disconnectOnPowerOff());
			self.connectOnPowerOn(self.settings.settings.plugins.tplinksmartplug.connectOnPowerOn());
			self.connectOnPowerOnDelay(self.settings.settings.plugins.tplinksmartplug.connectOnPowerOnDelay());
			self.enablePowerOffWarningDialog(self.settings.settings.plugins.tplinksmartplug.enablePowerOffWarningDialog());
			self.gcodeprocessing(self.settings.settings.plugins.tplinksmartplug.gcodeprocessing());
			self.checkStatus();
		}
		
		self.onDataUpdaterPluginMessage = function(plugin, data) {
            if (plugin != "tplinksmartplug") {
                return;
            }

			self.currentState(data.currentState);

			switch(self.currentState()) {
				case "on":
					self.relayState("#00FF00");
					break;
				case "off":
					self.relayState("#FF0000");
					self.poweroff_dialog.modal("hide");
					break;
				default:
					self.relayState("#808080");
			}          
        };
		
		self.toggleRelay = function() {
			switch(self.currentState()){
				case "on":
					if(self.enablePowerOffWarningDialog()){
						self.poweroff_dialog.modal("show");
					} else {
						self.turnOff();
					}					
					break;
				case "off":
					self.turnOn();
					break;
				default:
					new PNotify({
						title: 'TP-Link Smartplug Error',
						text: 'Status ' + self.currentState() + '. Double check IP Address\Hostname in TPLinkSmartplug Settings.',
						type: 'error',
						hide: false
						});
			}
		}
		
		self.turnOn = function() {
            $.ajax({
                url: API_BASEURL + "plugin/tplinksmartplug",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({
                    command: "turnOn"
                }),
                contentType: "application/json; charset=UTF-8"
            });
        };

    	self.turnOff = function() {
            $.ajax({
                url: API_BASEURL + "plugin/tplinksmartplug",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({
                    command: "turnOff"
                }),
                contentType: "application/json; charset=UTF-8"
            });
        }; 
		
		self.checkStatus = function() {
            $.ajax({
                url: API_BASEURL + "plugin/tplinksmartplug",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({
                    command: "checkStatus"
                }),
                contentType: "application/json; charset=UTF-8"
            });
        }; 
    }

    // view model class, parameters for constructor, container to bind to
    OCTOPRINT_VIEWMODELS.push([
        tplinksmartplugViewModel,

        // e.g. loginStateViewModel, settingsViewModel, ...
        ["settingsViewModel","loginStateViewModel"],

        // "#navbar_plugin_tplinksmartplug","#settings_plugin_tplinksmartplug"
        ["#navbar_plugin_tplinksmartplug","#settings_plugin_tplinksmartplug"]
    ]);
});
