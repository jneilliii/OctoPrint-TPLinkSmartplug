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
		self.validIP = ko.observable();
		self.cmdOnPowerOn = ko.observable();
		self.cmdOnPowerOnCommand = ko.observable();
		self.cmdOnPowerOff = ko.observable();
		self.cmdOnPowerOffCommand = ko.observable();
		self.arrSmartplugs = ko.observableArray();
		
		self.onBeforeBinding = function() {
			self.ip(self.settings.settings.plugins.tplinksmartplug.ip());
			self.validIP(self.settings.settings.plugins.tplinksmartplug.validIP());
			self.disconnectOnPowerOff(self.settings.settings.plugins.tplinksmartplug.disconnectOnPowerOff());
			self.connectOnPowerOn(self.settings.settings.plugins.tplinksmartplug.connectOnPowerOn());
			self.connectOnPowerOnDelay(self.settings.settings.plugins.tplinksmartplug.connectOnPowerOnDelay());
			self.cmdOnPowerOn(self.settings.settings.plugins.tplinksmartplug.cmdOnPowerOn());
			self.cmdOnPowerOnCommand(self.settings.settings.plugins.tplinksmartplug.cmdOnPowerOnCommand());
			self.cmdOnPowerOff(self.settings.settings.plugins.tplinksmartplug.cmdOnPowerOff());
			self.cmdOnPowerOffCommand(self.settings.settings.plugins.tplinksmartplug.cmdOnPowerOffCommand());
			self.enablePowerOffWarningDialog(self.settings.settings.plugins.tplinksmartplug.enablePowerOffWarningDialog());
			self.gcodeprocessing(self.settings.settings.plugins.tplinksmartplug.gcodeprocessing());
			self.arrSmartplugs(self.settings.settings.plugins.tplinksmartplug.arrSmartplugs());
        }
		
		self.onAfterBinding = function() {
			self.checkStatus();
			self.poweroff_dialog = $("#tplinksmartplug_poweroff_confirmation_dialog");
		}

        self.onEventSettingsUpdated = function (payload) {
			self.ip(self.settings.settings.plugins.tplinksmartplug.ip());			
			self.validIP(self.settings.settings.plugins.tplinksmartplug.validIP());
			self.disconnectOnPowerOff(self.settings.settings.plugins.tplinksmartplug.disconnectOnPowerOff());
			self.connectOnPowerOn(self.settings.settings.plugins.tplinksmartplug.connectOnPowerOn());
			self.connectOnPowerOnDelay(self.settings.settings.plugins.tplinksmartplug.connectOnPowerOnDelay());			
			self.cmdOnPowerOn(self.settings.settings.plugins.tplinksmartplug.cmdOnPowerOn());
			self.cmdOnPowerOnCommand(self.settings.settings.plugins.tplinksmartplug.cmdOnPowerOnCommand());
			self.cmdOnPowerOff(self.settings.settings.plugins.tplinksmartplug.cmdOnPowerOff());
			self.cmdOnPowerOffCommand(self.settings.settings.plugins.tplinksmartplug.cmdOnPowerOffCommand());
			self.enablePowerOffWarningDialog(self.settings.settings.plugins.tplinksmartplug.enablePowerOffWarningDialog());
			self.gcodeprocessing(self.settings.settings.plugins.tplinksmartplug.gcodeprocessing());
			self.arrSmartplugs(self.settings.settings.plugins.tplinksmartplug.arrSmartplugs());
			self.checkStatus();
		}
		
		self.addPlug = function() {
			self.arrSmartplugs.push({
				ip: "",
				gcodeEnabled: false,
				autoConnect: true,
				autoDisconnect: true,
				sysCmdOn: "",
				sysCmdOff: ""
			});
			console.log("add plug pressed.")
		}
		
		self.removePlug = function(plug) {
			console.log(plug);
			self.arrSmartplugs.remove(plug);
		}
		
		self.onDataUpdaterPluginMessage = function(plugin, data) {
            if (plugin != "tplinksmartplug") {
                return;
            }

			self.currentState(data.currentState);

			switch(self.currentState()) {
				case "on":
					self.relayState("#00FF00");
					self.validIP(true);
					break;
				case "off":
					self.relayState("#FF0000");
					self.validIP(true);
					self.poweroff_dialog.modal("hide");
					break;
				default:
					new PNotify({
						title: 'TP-Link Smartplug Error',
						text: 'Status ' + self.currentState() + '. Double check IP Address\\Hostname in TPLinkSmartplug Settings.',
						type: 'error',
						hide: true
						});
					self.relayState("#808080");
					self.validP(false);
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
