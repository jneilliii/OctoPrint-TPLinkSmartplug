# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/en/1.0.0/)
and this project adheres to [Semantic Versioning](http://semver.org/spec/v2.0.0.html).

## [Unreleased] - 2017-09-09
### Added
- Incorporated hostname support.  You can now use ip address or hostname.
- Additional debugging logged to octoprint.log.
- Added changelog.md.

### Changed
- Settings dialog changes for additional hostname support.
- Settings screenshot updated for above changes.
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

[Unreleased]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/hostname
[0.2.0]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.2.0
[0.1.0]: https://github.com/jneilliii/OctoPrint-TPLinkSmartplug/tree/0.1.0