source: https://developer.apple.com/documentation/bundleresources/privacy-manifest-files
## What a privacy manifest is
A privacy manifest is a property list named PrivacyInfo.xcprivacy that ships inside an app or SDK bundle. It records the data types the code collects, whether that data is used for tracking, the tracking domains it contacts, and the required-reason APIs it calls. Xcode merges the manifests of the app and its SDKs into the privacy report.

## Required-reason APIs
Some system APIs can be misused for fingerprinting, so Apple requires an approved reason for calling them. The categories are file timestamp APIs (stat, fstat, getattrlist, file creation and modification dates), system boot time APIs (mach_absolute_time, systemUptime), disk space APIs (statfs, statvfs, volume capacity keys), active keyboard APIs (activeInputModes) and user defaults APIs (NSUserDefaults). Each category the app uses must appear under NSPrivacyAccessedAPITypes with one or more approved reason codes. Since May 1, 2024 uploads to App Store Connect must include these reasons, including for third-party SDK code.

## Tracking declarations
If NSPrivacyTracking is true, the manifest should list the internet domains used for tracking in NSPrivacyTrackingDomains. Tracking also requires asking permission through the App Tracking Transparency framework, which needs the NSUserTrackingUsageDescription purpose string in Info.plist.

## Limits of static detection
A symbol in the import table shows that the binary links an API, not that it is called on a code path users reach. Selector-based APIs such as systemUptime and activeInputModes do not appear as imported symbols at all, so static analysis can miss them. Treat symbol-based findings as prompts to check the code.
