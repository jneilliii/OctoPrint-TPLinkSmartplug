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
		self.validIP = ko.observable();
		
		self.onBeforeBinding = function() {
            self.currentState(self.settings.settings.plugins.tplinksmartplug.currentState());
			self.validIP(self.settings.settings.plugins.tplinksmartplug.ip = '')
        }

        // TODO: Implement your plugin's view model here.
    }

    // view model class, parameters for constructor, container to bind to
    OCTOPRINT_VIEWMODELS.push([
        tplinksmartplugViewModel,

        // e.g. loginStateViewModel, settingsViewModel, ...
        ["settingsViewModel"],

        // "#navbar_plugin_tplinksmartplug","#settings_plugin_tplinksmartplug"
        ["#navbar_plugin_tplinksmartplug"]
    ]);
});
