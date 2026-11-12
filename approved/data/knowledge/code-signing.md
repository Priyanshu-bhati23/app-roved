source: https://developer.apple.com/documentation/xcode/distributing-your-app-for-beta-testing-and-releases
## Distribution signing
An app uploaded to App Store Connect must be signed with a distribution certificate and an App Store provisioning profile. Xcode applies these when you export an archive using the App Store Connect distribution method.

## Development entitlements
The get-task-allow entitlement lets a debugger attach to the process. It is true in development builds and must not be present in an App Store build. Finding it set to true in the embedded entitlements means the IPA was exported with a development or ad-hoc profile.

## Unsigned binaries
A Mach-O without an LC_CODE_SIGNATURE load command carries no signature at all. This usually means the IPA was assembled by hand or produced by a build step that skipped signing.
