# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [0.9.2] - 2018-02-03
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
