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
		
		self.debug = function() {
			alert(self.ip());
		}
		
		self.onBeforeBinding = function() {
            self.currentState(self.settings.settings.plugins.tplinksmartplug.currentState());
			self.ip(self.settings.settings.plugins.tplinksmartplug.ip);
        }

        self.onEventSettingsUpdated = function (payload) {
			self.ip(self.settings.settings.plugins.tplinksmartplug.ip);
		}
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
