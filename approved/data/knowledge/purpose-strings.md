source: https://developer.apple.com/documentation/bundleresources/information-property-list
## Purpose strings for protected resources
Before an app can read protected resources such as the camera, microphone, location, photos, contacts, calendars, motion data, Bluetooth, Face ID or health data, its Info.plist must contain the matching usage-description key. The system shows that text in the permission prompt. If the key is missing when the app touches the resource, the system terminates the app.

## Quality of purpose strings
App Review Guideline 5.1.1 requires apps to clearly explain why they need access to user data. A purpose string that is empty, generic or placeholder text does not explain the use and is a common reason for rejection. The string should name the feature that uses the data.

## Core bundle keys
Every bundle's Info.plist identifies it with CFBundleIdentifier, names its executable with CFBundleExecutable, and carries a marketing version in CFBundleShortVersionString and a build number in CFBundleVersion. App Store Connect uses the version and build number to tell uploads apart.

## Export compliance
ITSAppUsesNonExemptEncryption declares whether the app uses non-exempt encryption. When the key is absent, App Store Connect asks the export-compliance questions for each uploaded build before it can be distributed.

## App Transport Security
App Transport Security requires HTTPS connections with modern TLS by default. Setting NSAllowsArbitraryLoads to true disables that protection for all connections; Apple documents that broad exceptions can trigger additional App Review and need a justification. Per-domain exceptions are the narrower alternative.
