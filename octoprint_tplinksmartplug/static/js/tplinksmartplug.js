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

		self.arrSmartplugs = ko.observableArray();
		self.isPrinting = ko.observable(false);
		self.selectedPlug = ko.observable();
		self.processing = ko.observableArray([]);
		self.test = ko.observableDictionary();
		self.filteredSmartplugs = ko.computed(function(){
			return ko.utils.arrayFilter(self.test.items(), function(item) {
						return "err_code" in item.value().emeter.get_realtime;
					});
		});
		self.show_sidebar = ko.computed(function(){
			return self.filteredSmartplugs().length > 0;
		});
		self.monitorarray = ko.computed(function(){return ko.toJSON(self.arrSmartplugs);}).subscribe(function(){console.log('monitored array');console.log(ko.toJSON(self.test));})
		self.get_power = function(data){ // make computedObservable()?
			if("power" in data.emeter.get_realtime && typeof data.emeter.get_realtime.power == "function"){
				return data.emeter.get_realtime.power().toFixed(2);
			} else if ("power_mw" in data.emeter.get_realtime && typeof data.emeter.get_realtime.power_mw == "function") {
				return (data.emeter.get_realtime.power_mw()/1000).toFixed(2);
			} else if("power" in data.emeter.get_realtime && typeof data.emeter.get_realtime.power !== "function"){
				return data.emeter.get_realtime.power.toFixed(2);
			} else if ("power_mw" in data.emeter.get_realtime && typeof data.emeter.get_realtime.power_mw !== "function") {
				return (data.emeter.get_realtime.power_mw/1000).toFixed(2);
			} else {
				return "-"
			}
		}
		self.get_kwh = function(data){ // make computedObservable()?
			if("total" in data.emeter.get_realtime && typeof data.emeter.get_realtime.total == "function"){
				return data.emeter.get_realtime.total().toFixed(2);
			} else if ("total_wh" in data.emeter.get_realtime && typeof data.emeter.get_realtime.total_wh == "function") {
				return (data.emeter.get_realtime.total_wh()/1000).toFixed(2);
			} else if("total" in data.emeter.get_realtime && typeof data.emeter.get_realtime.total !== "function"){
				return data.emeter.get_realtime.total.toFixed(2);
			} else if ("total_wh" in data.emeter.get_realtime && typeof data.emeter.get_realtime.total_wh !== "function") {
				return (data.emeter.get_realtime.total_wh/1000).toFixed(2);
			} else {
				return "-"
			}
		}

		self.onBeforeBinding = function() {
			self.arrSmartplugs(self.settings.settings.plugins.tplinksmartplug.arrSmartplugs());
		}

		self.onAfterBinding = function() {
			self.checkStatuses();
		}

		self.onEventSettingsUpdated = function(payload) {
			self.arrSmartplugs(self.settings.settings.plugins.tplinksmartplug.arrSmartplugs());
		}

		self.onEventPrinterStateChanged = function(payload) {
			if (payload.state_id == "PRINTING" || payload.state_id == "PAUSED"){
				self.isPrinting(true);
			} else {
				self.isPrinting(false);
			}
		}

		self.cancelClick = function(data) {
			self.processing.remove(data.ip());
		}

		self.editPlug = function(data) {
			self.selectedPlug(data);
			$("#TPLinkPlugEditor").modal("show");
		}

		self.addPlug = function() {
			self.selectedPlug({'ip':ko.observable(''),
								'label':ko.observable(''),
								'icon':ko.observable('icon-bolt'),
								'displayWarning':ko.observable(true),
								'warnPrinting':ko.observable(false),
								'gcodeEnabled':ko.observable(false),
								'gcodeOnDelay':ko.observable(0),
								'gcodeOffDelay':ko.observable(0),
								'autoConnect':ko.observable(true),
								'autoConnectDelay':ko.observable(10.0),
								'autoDisconnect':ko.observable(true),
								'autoDisconnectDelay':ko.observable(0),
								'sysCmdOn':ko.observable(false),
								'sysRunCmdOn':ko.observable(''),
								'sysCmdOnDelay':ko.observable(0),
								'sysCmdOff':ko.observable(false),
								'sysRunCmdOff':ko.observable(''),
								'sysCmdOffDelay':ko.observable(0),
								'currentState':ko.observable('unknown'),
								'btnColor':ko.observable('#808080'),
								'useCountdownRules':ko.observable(false),
								'countdownOnDelay':ko.observable(0),
								'countdownOffDelay':ko.observable(0),
								'emeter':{get_realtime:{}}});
			self.settings.settings.plugins.tplinksmartplug.arrSmartplugs.push(self.selectedPlug());
			$("#TPLinkPlugEditor").modal("show");
		}

		self.removePlug = function(row) {
			self.settings.settings.plugins.tplinksmartplug.arrSmartplugs.remove(row);
		}

		self.onDataUpdaterPluginMessage = function(plugin, data) {
			if (plugin != "tplinksmartplug") {
				return;
			}
			console.log('Websocket message received, checking status of ' + data.ip);
			self.checkStatus(data.ip);
		};

		self.toggleRelay = function(data) {
			self.processing.push(data.ip());
			switch(data.currentState()){
				case "on":
					self.turnOff(data);
					break;
				case "off":
					self.turnOn(data);
					break;
				default:
					self.checkStatus(data.ip());
			}
		}

		self.turnOn = function(data) {
			self.sendTurnOn(data);
		}

		self.sendTurnOn = function(data) {
			$.ajax({
				url: API_BASEURL + "plugin/tplinksmartplug",
				type: "POST",
				dataType: "json",
				data: JSON.stringify({
					command: "turnOn",
					ip: data.ip()
				}),
				contentType: "application/json; charset=UTF-8"
			}).done(function(data){
					console.log('Turn on command completed.');
					console.log(data);
					self.processing.remove(data.ip);
				});
		};

		self.turnOff = function(data) {
			if((data.displayWarning() || (self.isPrinting() && data.warnPrinting())) && !$("#TPLinkSmartPlugWarning").is(':visible')){
				self.selectedPlug(data);
				$("#TPLinkSmartPlugWarning").modal("show");
			} else {
				$("#TPLinkSmartPlugWarning").modal("hide");
				self.sendTurnOff(data);
			}
		}; 

		self.sendTurnOff = function(data) {
			$.ajax({
			url: API_BASEURL + "plugin/tplinksmartplug",
			type: "POST",
			dataType: "json",
			data: JSON.stringify({
				command: "turnOff",
				ip: data.ip()
			}),
			contentType: "application/json; charset=UTF-8"
			}).done(function(data){
					console.log('Turn off command completed.');
					console.log(data);
					self.processing.remove(data.ip);
				});
		}

		self.checkStatus = function(plugIP) {
			$.ajax({
				url: API_BASEURL + "plugin/tplinksmartplug",
				type: "GET",
				dataType: "json",
				data: {checkStatus:plugIP},
				contentType: "application/json; charset=UTF-8"
			}).done(function(data){
				ko.utils.arrayForEach(self.arrSmartplugs(),function(item){
						if(item.ip() == data.ip) {
							item.currentState(data.currentState);
							if(data.emeter){
								item.emeter.get_realtime = {};
								for (key in data.emeter.get_realtime){
									//console.log(key + ' = ' + data.emeter.get_realtime[key]);
									item.emeter.get_realtime[key] = ko.observable(data.emeter.get_realtime[key]);
								}
							}
							self.processing.remove(data.ip);
						}
					});
					self.test.removeAll();
					self.test.pushAll(ko.toJS(self.arrSmartplugs));
				});
		}; 

		self.checkStatuses = function() {
			ko.utils.arrayForEach(self.arrSmartplugs(),function(item){
				if(item.ip() !== "") {
					console.log("checking " + item.ip())
					self.checkStatus(item.ip());
				}
			});
			if (self.settings.settings.plugins.tplinksmartplug.pollingEnabled()) {
				setTimeout(function() {self.checkStatuses();}, (parseInt(self.settings.settings.plugins.tplinksmartplug.pollingInterval(),10) * 60000));
			};
		};
	}

	OCTOPRINT_VIEWMODELS.push([
		tplinksmartplugViewModel,
		["settingsViewModel","loginStateViewModel"],
		["#navbar_plugin_tplinksmartplug","#settings_plugin_tplinksmartplug","#sidebar_plugin_tplinksmartplug_wrapper"]
	]);
});
