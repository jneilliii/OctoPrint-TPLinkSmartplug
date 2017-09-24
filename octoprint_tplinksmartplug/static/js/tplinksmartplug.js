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
			self.checkStatuses();
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
			self.checkStatuses();
		}
		
		self.addPlug = function() {
			self.settings.settings.plugins.tplinksmartplug.arrSmartplugs.push({'ip':'',
																				'gcodeEnabled':false,
																				'autoConnect':true,
																				'autoConnectDelay':10.0,
																				'autoDisconnect':true,
																				'autoDisconnectDelay':0,
																				'sysCmdOn':'',
																				'sysCmdOnDelay':0,
																				'sysCmdOff':'',
																				'sysCmdOffDelay':0,
																				'currentState':'unknown'});
		}
		
		self.removePlug = function(row) {
			self.settings.settings.plugins.tplinksmartplug.arrSmartplugs.remove(row);
		}
		
		self.onDataUpdaterPluginMessage = function(plugin, data) {
            if (plugin != "tplinksmartplug") {
                return;
            }

			ko.utils.arrayFirst(self.settings.settings.plugins.tplinksmartplug.arrSmartplugs(),function(plug){
				console.log(plug)
				if (plug.ip() == data.ip) {
					plug.currentState(data.currentState)
				}});
			
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
		
		self.toggleRelay = function(data) {
			switch(self.currentState()){
				case "on":
					// if(self.enablePowerOffWarningDialog()){
						// self.poweroff_dialog.modal("show");
					// } else {
						self.turnOff(data.ip());
					// }					
					break;
				case "off":
					self.turnOn(data.ip());
					break;
				default:
			}
		}
		
		self.turnOn = function(plugIP) {
            $.ajax({
                url: API_BASEURL + "plugin/tplinksmartplug",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({
                    command: "turnOn",
					ip: plugIP
                }),
                contentType: "application/json; charset=UTF-8"
            });
        };

    	self.turnOff = function(plugIP) {
            $.ajax({
                url: API_BASEURL + "plugin/tplinksmartplug",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({
                    command: "turnOff",
					ip: plugIP
                }),
                contentType: "application/json; charset=UTF-8"
            });
        }; 
		
		self.checkStatus = function(plugIP) {
            $.ajax({
                url: API_BASEURL + "plugin/tplinksmartplug",
                type: "POST",
                dataType: "json",
                data: JSON.stringify({
                    command: "checkStatus",
					ip: plugIP
                }),
                contentType: "application/json; charset=UTF-8"
            });
        }; 
		
		self.checkStatuses = function() {
			ko.utils.arrayForEach(self.settings.settings.plugins.tplinksmartplug.arrSmartplugs(),function(plug){
				$.ajax({
					url: API_BASEURL + "plugin/tplinksmartplug",
					type: "POST",
					dataType: "json",
					data: JSON.stringify({
						command: "checkStatus",
						ip: plug.ip()
					}),
					contentType: "application/json; charset=UTF-8"
				});
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
