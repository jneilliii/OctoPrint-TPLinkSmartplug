/*
 * View model for OctoPrint-TPLinkSmartplug
 *
 * Author: jneilliii
 * License: AGPLv3
 */
$(function() {
/* 	function plugViewModel() {
		var self = this;
		self.ip = ko.observable(ip);
		self.label = ko.observable(label);
		self.icon = ko.observable(icon);
		self.displayWarning = ko.observable(displayWarning);
		self.warnPrinting = ko.observable(warnPrinting);
		self.gcodeEnabled = ko.observable(gcodeEnabled);
		self.gcodeOnDelay = ko.observable(gcodeOnDelay);
		self.gcodeOffDelay = ko.observable(gcodeOffDelay);
		self.autoConnect = ko.observable(autoConnect);
		self.autoConnectDelay = ko.observable(autoConnectDelay);
		self.autoDisconnect = ko.observable(autoDisconnect);
		self.autoDisconnectDelay = ko.observable(autoDisconnectDelay);
		self.sysCmdOn = ko.observable(sysCmdOn);
		self.sysRunCmdOn = ko.observable(sysRunCmdOn);
		self.sysCmdOnDelay = ko.observable(sysCmdOnDelay);
		self.sysCmdOff = ko.observable(sysCmdOff);
		self.sysRunCmdOff = ko.observable(sysRunCmdOff);
		self.sysCmdOffDelay = ko.observable(sysCmdOffDelay);
		self.currentState = ko.observable(currentState);
		self.btnColor = ko.observable(btnColor);
		self.useCountdownRules = ko.observable(useCountdownRules);
		self.countdownOnDelay = ko.observable(countdownOnDelay);
		self.countdownOffDelay = ko.observable(countdownOffDelay);
		self.emeter = {get_realtime = {}};
		self.thermal_runaway = ko.observable(thermal_runaway)
	} */

	function tplinksmartplugViewModel(parameters) {
		var self = this;

		self.settings = parameters[0];
		self.loginState = parameters[1];

		self.arrSmartplugs = ko.observableArray();
		self.isPrinting = ko.observable(false);
		self.selectedPlug = ko.observable();
		self.processing = ko.observableArray([]);
		self.plotted_graph_ip = ko.observable(false);
		self.plotted_graph_records = ko.observable(10);
		self.plotted_graph_records_offset = ko.observable(0);
		self.dictSmartplugs = ko.observableDictionary();
		self.filteredSmartplugs = ko.computed(function(){
			return ko.utils.arrayFilter(self.dictSmartplugs.items(), function(item) {
						return "err_code" in item.value().emeter.get_realtime;
					});
		});
		self.energySmartplugs = ko.computed(function(){
			return ko.utils.arrayFilter(self.arrSmartplugs(), function(item) {
						return "err_code" in item.emeter.get_realtime;
					});
		});
		self.show_sidebar = ko.computed(function(){
			return self.filteredSmartplugs().length > 0;
		});

		self.allPlugsDisabled =  ko.computed(function() {
			var enablePlug = null;
			enablePlug = ko.utils.arrayFirst(self.arrSmartplugs(), function(item) {
				return item.currentState() == "on" && "err_code" in item.emeter.get_realtime;
			});
			if (enablePlug == null)
				return false;
			return true;
		})

		//self.monitorarray = ko.computed(function(){return ko.toJSON(self.arrSmartplugs);}).subscribe(function(){console.log('monitored array');console.log(ko.toJSON(self.dictSmartplugs));})
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

		self.get_cost = function(data){ // make computedObservable()?
			if("total" in data.emeter.get_realtime && typeof data.emeter.get_realtime.total == "function"){
				return (data.emeter.get_realtime.total() * self.settings.settings.plugins.tplinksmartplug.cost_rate());
			} else if ("total_wh" in data.emeter.get_realtime && typeof data.emeter.get_realtime.total_wh == "function") {
				return ((data.emeter.get_realtime.total_wh()/1000) * self.settings.settings.plugins.tplinksmartplug.cost_rate());
			} else if("total" in data.emeter.get_realtime && typeof data.emeter.get_realtime.total !== "function"){
				return (data.emeter.get_realtime.total * self.settings.settings.plugins.tplinksmartplug.cost_rate());
			} else if ("total_wh" in data.emeter.get_realtime && typeof data.emeter.get_realtime.total_wh !== "function") {
				return ((data.emeter.get_realtime.total_wh/1000) * self.settings.settings.plugins.tplinksmartplug.cost_rate());
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

		self.onSettingsBeforeSave = function(payload) {
			var plugs_updated = (ko.toJSON(self.arrSmartplugs()) !== ko.toJSON(self.settings.settings.plugins.tplinksmartplug.arrSmartplugs()));
			self.arrSmartplugs(self.settings.settings.plugins.tplinksmartplug.arrSmartplugs());
			if(plugs_updated){
				console.log('onEventSettingsUpdated:');
				console.log('arrSmartplugs: ' + ko.toJSON(self.arrSmartplugs()));
				console.log('settings.settings.plugins.tplinksmartplug.arrSmartplugs: ' + ko.toJSON(self.settings.settings.plugins.tplinksmartplug.arrSmartplugs()));
				console.log('arrSmartplugs changed, checking statuses');
				self.checkStatuses();
			}
		}

		self.onEventPrinterStateChanged = function(payload) {
			if (payload.state_id == "PRINTING" || payload.state_id == "PAUSED"){
				self.isPrinting(true);
			} else {
				self.isPrinting(false);
			}
		}

		self.onTabChange = function(current, previous) {
				if (current === "#tab_plugin_tplinksmartplug") {
					self.plotEnergyData(false);
				}
			};

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
								'countdownOnDelay':ko.observable(1),
								'countdownOffDelay':ko.observable(1),
								'emeter':{get_realtime:{}},
								'thermal_runaway':ko.observable(false),
								'event_on_error':ko.observable(false),
								'event_on_disconnect':ko.observable(false)});
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

			if(data.currentState || data.check_status){
				// console.log('Websocket message received, checking status of ' + data.ip);
				self.checkStatus(data.ip);
			}
			if(data.updatePlot && window.location.href.indexOf('tplinksmartplug') > 0){
				self.plotEnergyData();
			}
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
					//console.log('Turn on command completed.');
					//console.log(data);
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
					//console.log('Turn off command completed.');
					//console.log(data);
					self.processing.remove(data.ip);
				});
		}

		self.plotEnergyData = function(data) {
			//console.log(data);
			if(self.plotted_graph_ip()) {
				$.ajax({
				url: API_BASEURL + "plugin/tplinksmartplug",
				type: "POST",
				dataType: "json",
				data: JSON.stringify({
					command: "getEnergyData",
					ip: self.plotted_graph_ip(),
					record_limit: self.plotted_graph_records(),
					record_offset: self.plotted_graph_records_offset()
				}),
				cost_rate: self.settings.settings.plugins.tplinksmartplug.cost_rate(),
				contentType: "application/json; charset=UTF-8"
				}).done(function(data){
						console.log('Energy Data retrieved');
						console.log(data);
						console.log(this.cost_rate);

						//update plotly graph here.
						var trace_current = {x:[],y:[],mode:'lines+markers',name:'Current (Amp)',xaxis: 'x2',yaxis: 'y2'};
						var trace_power = {x:[],y:[],mode:'lines+markers',name:'Power (W)',xaxis: 'x3',yaxis: 'y3'}; 
						var trace_total = {x:[],y:[],mode:'lines+markers',name:'Total (kWh)'};
						//var trace_voltage = {x:[],y:[],mode:'lines+markers',name:'Voltage (V)',yaxis: 'y3'};;
						var trace_cost = {x:[],y:[],mode:'lines+markers',name:'Cost'}

						ko.utils.arrayForEach(data.energy_data, function(row){
							trace_current.x.push(row[0]);
							trace_current.y.push(row[1]);
							trace_power.x.push(row[0]);
							trace_power.y.push(row[2]);
							trace_total.x.push(row[0]);
							trace_total.y.push(row[3]);
							trace_cost.x.push(row[0]);
							trace_cost.y.push(row[3]*this.cost_rate);
							//trace_voltage.x.push(row[0]);
							//trace_voltage.y.push(row[4]);
						});

						var layout = {title:'TP-Link Smartplug Energy Data',
									grid: {rows: 2, columns: 1, pattern: 'independent'},
									xaxis: {
										showticklabels: false,
										anchor: 'x'
									},
									yaxis: {
										title: 'Total (kWh)',
										hoverformat: '.3f kWh',
										tickangle: 45,
										tickfont: {
											size: 10
										},
										tickformat: '.2f',
										anchor: 'y'
									},
									xaxis2: {
										anchor: 'y2'
									},
									yaxis2: {
										title: 'Current (Amp)',
										hoverformat: '.3f',
										anchor: 'x2',
										tickangle: 45,
										tickfont: {
											size: 10
										},
										tickformat: '.2f'
									},
									xaxis3: {
										overlaying: 'x2',
										anchor: 'y3',
										showticklabels: false
									},
									yaxis3: {
										overlaying: 'y2',
										side: 'right',
										title: 'Power (W)',
										hoverformat: '.3f',
										anchor: 'x3',
										tickangle: -45,
										tickfont: {
											size: 10
										},
										tickformat: '.2f'
									},
									xaxis4: {
										overlaying: 'x',
										anchor: 'y4',
										showticklabels: false
									},
									yaxis4: {
										overlaying: 'y',
										side: 'right',
										title: 'Cost',
										hoverformat: '.3f',
										anchor: 'x4',
										tickangle: -45,
										tickfont: {
											size: 10
										},
										tickformat: '.2f'
									}};

						var plot_data = [trace_total,trace_current,trace_power,trace_cost/* ,trace_voltage */]
						Plotly.react('tplinksmartplug_energy_graph',plot_data,layout);
					});
			}
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
								if(data.ip == self.plotted_graph_ip() && self.settings.settings.plugins.tplinksmartplug.pollingEnabled() && window.location.href.indexOf('tplinksmartplug') > 0){
									self.plotEnergyData();
								}
							}
							self.processing.remove(data.ip);
						}
					});
					self.dictSmartplugs.removeAll();
					self.dictSmartplugs.pushAll(ko.toJS(self.arrSmartplugs));
				});
		}; 

		self.checkStatuses = function() {
			ko.utils.arrayForEach(self.arrSmartplugs(),function(item){
				if(item.ip() !== "") {
					//console.log("checking " + item.ip())
					self.checkStatus(item.ip());
				}
			});
			if (self.settings.settings.plugins.tplinksmartplug.pollingEnabled() && parseInt(self.settings.settings.plugins.tplinksmartplug.pollingInterval(),10) > 0) {
				setTimeout(function() {self.checkStatuses();}, (parseInt(self.settings.settings.plugins.tplinksmartplug.pollingInterval(),10) * 60000));
			};
		};
	}

	OCTOPRINT_VIEWMODELS.push([
		tplinksmartplugViewModel,
		["settingsViewModel","loginStateViewModel"],
		["#navbar_plugin_tplinksmartplug","#settings_plugin_tplinksmartplug","#sidebar_plugin_tplinksmartplug_wrapper","#tab_plugin_tplinksmartplug"]
	]);
});
