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
		self.currentState = ko.observable();
		self.ip = ko.observable();
		self.relayState = ko.observable("");
		
		self.onBeforeBinding = function() {
            self.currentState(self.settings.settings.plugins.tplinksmartplug.currentState());
			self.ip(self.settings.settings.plugins.tplinksmartplug.ip());
        }

        self.onEventSettingsUpdated = function (payload) {
			self.ip(self.settings.settings.plugins.tplinksmartplug.ip());
		}
		
		self.onDataUpdaterPluginMessage = function(plugin, data) {
            if (plugin != "tplinksmartplug") {
                return;
            }

			console.log(data.relayState);
			if (currentState()) {
				self.relayState("#00FF00");
			} else {
				self.relayState("#808080");
			}            
        };
		
		self.toggleRelay =function() {
			if(self.currentState()) {
				self.turnOn();
			} else {
				self.turnOff();
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
			self.currentState(true);
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
			self.currentState(false);
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
