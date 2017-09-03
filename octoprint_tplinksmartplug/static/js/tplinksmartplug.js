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
		self.currentState = ko.observable("unknown");
		self.ip = ko.observable();
		self.relayState = ko.observable("");
		
		self.onBeforeBinding = function() {
			self.ip(self.settings.settings.plugins.tplinksmartplug.ip());
        }

        self.onEventSettingsUpdated = function (payload) {
			self.ip(self.settings.settings.plugins.tplinksmartplug.ip());
		}
		
		self.onDataUpdaterPluginMessage = function(plugin, data) {
            if (plugin != "tplinksmartplug") {
                return;
            }

			self.currentState(data.currentState);

			switch(self.currentState()) {
				case "on":
					self.relayState("#00FF00");
				case "off":
					self.relayState("#808080");
				default:
					self.relayState("#FF0000");
			}          
        };
		
		self.toggleRelay = function() {
			switch(self.currentState()){
				case "on":
					self.turnOff();
				case "off":
					self.turnOn();
				default:
					console.log(self.currentState());
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
    }

    // view model class, parameters for constructor, container to bind to
    OCTOPRINT_VIEWMODELS.push([
        tplinksmartplugViewModel,

        // e.g. loginStateViewModel, settingsViewModel, ...
        ["settingsViewModel"],

        // "#navbar_plugin_tplinksmartplug","#settings_plugin_tplinksmartplug"
        ["#navbar_plugin_tplinksmartplug","#settings_plugin_tplinksmartplug"]
    ]);
});
