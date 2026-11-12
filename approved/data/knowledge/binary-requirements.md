source: https://developer.apple.com/app-store/review/guidelines/
## Public APIs only
Guideline 2.5.1 says apps may only use public APIs and must run on the currently shipping OS. Loading a library from /System/Library/PrivateFrameworks is use of a private framework. The link is frequently introduced by a third-party SDK rather than first-party code.

## UIWebView
UIWebView is a deprecated class. Apple stopped accepting new apps and app updates that reference it, and the App Store upload reports the deprecated API usage. WKWebView is the replacement. Old analytics and advertising SDKs are the usual source of a leftover reference.

## Minimum SDK and deployment target
Apple publishes upcoming requirements for the minimum Xcode and SDK version an upload must be built with, and for the lowest deployment target it accepts. Since April 28, 2026 uploads must be built with Xcode 26 and the iOS 26 SDK or later; from September 9, 2026 iOS and iPadOS apps must target iOS 13 or later. These thresholds move, so App-roved reads them from configuration.

## Device architectures
App Store builds contain device architectures only. A framework that still carries x86_64 or i386 simulator slices is widely reported by developers to fail upload validation as an unsupported architecture. XCFrameworks avoid the problem because Xcode selects the right slice at build time.

## Background modes
Guideline 2.5.4 says multitasking apps may only use background services for their intended purposes, such as VoIP, audio playback, location, task completion and local notifications. Each entry in UIBackgroundModes should correspond to a feature a reviewer can find.

## App completeness and hidden features
Guideline 2.1 expects submissions to be final versions with placeholder text removed. Guideline 2.3.1 prohibits hidden, dormant or undocumented features; new features and functionality should be described in the review notes. How much weight reviewers give to the presence of a remote-configuration SDK is not something that can be verified publicly.
