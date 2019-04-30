# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [0.9.16] - 2019-04-30
### Added
- Strip support.
- Energy data logging and graphing via new tab.
- Temperature runaway protection.

## [0.9.13] - 2019-02-16
### Fixed
- Update button state when plug powered on/off via gcode.

## [0.9.12] - 2019-02-10
### Fixed
- Issue introduced in previous version prevented fresh installs from working properly.

## [0.9.11] - 2019-02-09
### Fixed
- Energy monitoring sidebar not displaying consistently.

## [0.9.10] - 2018-11-25
### Changed
- Energy monitoring sidebar text controlled via css style instead of inline element styles to allow control via Themeify.

## [0.9.9] - 2018-11-20
### Changed
- Changed current status logic checks to resolve potential issues with upcoming bundled force login plugin of OctoPrint 1.3.10.

## [0.9.8] - 2018-11-18
### Fixed
- Non Energy Monitoring devices were causing errors on status checks resulting in status update failure.

### Issues
- When toggling energy monitoring devices on/off the energy usage reported in the sidebar panel is from prior to the status change, so off plugs aren't reporting 0 as expected. Upon the next polling interval the power usage shoould be back in sync.

## [0.9.7] - 2018-11-03
### Added
- Added energy monitoring support for the HS-110 devices.  Plugs' statuses will be checked on startup, on toggle of on/off, on print progress, and on polling interval configured in settings.  

## [0.9.6] - 2018-08-05
### Added
- Added countdown timer option to plug settings to allow using the plug's built in functions for delayed power on/off.

### Notes
- **Previously configured plugs will be erased upon upgrade to account for new data structure.**

## [0.9.5] - 2018-08-03
### Added
- Custom gcode commands `@TPLINKON` and `@TPLINKOFF` for custom cases where M80/M81 can't be used.

## [0.9.4] - 2018-06-09
### Changed
- If M81 command is received to power off plug with a configured delay and `Warn While Printing` is enabled the plug will not be powered off if another print is started before the delay is reached.

## [0.9.3] - 2018-02-03
### Fixed
- Icon not displaying in IE due to binding css issue.

## [0.9.2] - 2018-01-31
### Notes
- **Previously configured plugs will be erased upon upgrade to account for new data structure.**

### Added
- Button labeling.
- Button icons configurable via fontawesome class names found [here](http://fontawesome.io/3.2.1/cheatsheet/).
- Spinning icon while awaiting response from server.

### Changed
- Improved settings layout, less clutter.

## [0.9.1] - 2018-01-30
### Notes
- **Previously configured plugs will be erased upon upgrade to account for new data structure.**

### Added
- Button labeling.
- Button icons configurable via fontawesome class names found [here](http://fontawesome.io/3.2.1/cheatsheet/).
- Spinning icon while awaiting response from server.

### Changed
- Improved settings layout, less clutter.

## [0.8.0] - 2018-01-29
### Added
- Status polling of all configured plugs.

## [0.7.3] - 2017-12-21
### Changed
- Moved all command processing to server side to resolve gcode processing issues when web front-end wasn't loaded.

## [0.7.2] - 2017-10-24
### Fixed
- Thanks to Gina, really fix the issue with software upgrade where viewmodel binding was breaking.

## [0.7.1] - 2017-10-22
### Fixed
- Issue with software upgrade where viewmodel binding was breaking.

## [0.7.0] - 2017-10-22
### Added
- Warning while printing, disable in settings (right checkbox in Warn column).
- Settings versioning
- Clear smartplug array on upgrade to account for data structure changes (crude hack until future data structure improvements).

### Changed
- Settings dialog for additional warning setting.
- Toggle off function changed to escape special characters required for jquery selectors.

### Fixed
- Toggle off issue when using ip address and warning prompt due to jquery selectors.

## [0.6.0] - unreleased
### Added
- Support for multiple plugs incorporated.

### Changed
- Settings dialog updated for multiple plug support.
- Navbar icons updated for multiple plug support.
- Screenshots updated for multiple plug support.
- When plug status is unknown navbar buttons will check status of plug when clicked.

### Removed
- Removed tabbed interface in settings.

## [0.5.0] - 2017-09-22
### Changed
- Modified encrypt function to work with hardware version 2 SmartPlugs.

## [0.4.0] - 2017-09-16
### Added
- Added system command options on power on and off.

### Changed
- Modified settings dialog for above additions.
- Converted settings dialog to tabbed interface.
- Updated screenshots.
- Updated readme to add additional settings screenshots.

## [0.3.1] - 2017-09-13
### Added
- Added missing import reference to flask.make_response.

## [0.3.0] - 2017-09-12
### Added
- Incorporated hostname support.  You can now use ip address or hostname.
- Additional debugging logged to separate log file.
- Added processing of M80 and M81 gcode commands.
- Added changelog.md.

### Changed
- Settings dialog updated for additional hostname support and M80/M81 gcode processing.
- Settings screenshot updated for above additions and changes.
- error notification reference on connection error to include hostname in description.
- Increment version in setup.py.

### Removed
- Took out unused css references created by cookiecutter.

## [0.2.0] - 2017-09-06
### Added
- Added error notification popup on unknown status, typically meaning a communication error due to bad ip address.

### Changed
- Updated readme.md and screenshots.
- Increment version in setup.py.

## [0.1.0] - 2017-09-03
### Added
- Initial release.

[0.9.16]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.9.16
[0.9.13]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.9.13
[0.9.12]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.9.12
[0.9.11]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.9.11
[0.9.10]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.9.10
[0.9.9]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.9.9
[0.9.8]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.9.8
[0.9.7]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.9.7
[0.9.6]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.9.6
[0.9.5]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.9.5
[0.9.4]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.9.4
[0.9.3]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.9.3
[0.9.2]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.9.2
[0.9.1]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.9.1
[0.8.0]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.8.0
[0.7.3]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.7.3
[0.7.2]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.7.2
[0.7.1]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.7.1
[0.7.0]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.7.0
[0.5.0]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.5.0
[0.4.0]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.4.0
[0.3.1]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.3.1
[0.3.0]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.3.0
[0.2.0]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.2.0
[0.1.0]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.1.0
