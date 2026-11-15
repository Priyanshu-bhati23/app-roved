source: https://developer.apple.com/app-store/review/guidelines/
## 2.1 App Completeness
Apps sent to review must be finished and work: no crashes, no obvious bugs, no broken links, and no placeholder text or empty screens. If any part of the app needs a login, the reviewer needs a working demo account (or a demo mode) entered in App Store Connect under App Review Information, plus notes for anything that is hard to reach. Many rejections under 2.1 are simply the reviewer being unable to get past a login, a paywall or a server that was down.

## 2.2 Beta Testing
Demos, betas and trial versions do not belong on the App Store. Builds that are still being tested should go through TestFlight. Calling the app a beta, a test version or "coming soon" in the app or its metadata invites a rejection.

## 2.3 Accurate Metadata
The App Store page must describe the app truthfully. Screenshots should show the app in use, not only a title or splash screen. All features must be visible to the reviewer and described: hidden, dormant or undocumented features are not allowed (2.3.1). The name, subtitle, keywords and description must not mention other mobile platforms such as Android or Google Play (2.3.10), and must not carry placeholder text.

## 3.1.1 In-App Purchase
Unlocking features or functionality inside the app, such as premium content, subscriptions, game currency or full versions, generally has to use Apple's in-app purchase. Physical goods and services used outside the app can use other payment methods. The rules for linking to outside payment options differ by country and storefront, so check the current text of 3.1.1 and 3.1.3 for each market.

## 3.1.2 Subscriptions
Auto-renewing subscriptions must give ongoing value and must clearly tell users what they get, the price, the length and that it renews. The App Store metadata needs a working link to the Terms of Use (EULA) and to the privacy policy, and the app should show them where people subscribe. Apple's standard EULA can be linked in the App Description, or a custom EULA can be added in App Store Connect.

## 4.2 Minimum Functionality
An app should offer more than a repackaged website. Apps that are mostly a web view, a list of links or a thin wrapper around web content are often rejected under 4.2. Native features, offline use or functionality that only makes sense as an app help.

## 4.3 Spam
Apple rejects apps that duplicate other apps, including several near-identical apps from one developer, and apps in saturated categories that add nothing new. Explaining what is different, consolidating similar apps into one, and making the unique value obvious in the app and its screenshots are the usual responses.

## 4.8 Login Services
Apps that use a third-party or social login, such as Google or Facebook, to set up or authenticate the main account must also offer an equivalent login option that limits data collection to name and email, lets people keep their email private, and does not track them without consent. Sign in with Apple meets these requirements.

## 5.1.1 Data Collection and Storage
Every app needs a privacy policy link in App Store Connect and inside the app. Apps must ask permission before collecting user data, and each permission prompt needs a purpose string that clearly explains why. Apps that let people create an account must also let them delete that account from within the app. Apps should not require people to log in or share personal data unless a feature really depends on it.

## 5.1.2 Data Use and Sharing
Tracking users across apps and websites owned by other companies requires permission through the App Tracking Transparency framework, with a clear NSUserTrackingUsageDescription. The App Privacy answers in App Store Connect must match what the app and every SDK inside it actually collect and how it is used.

## 1.2 User-Generated Content
Apps where people post content or talk to each other need a way to filter objectionable material, a way to report offensive content with timely responses, a way to block abusive users, and published contact information. Without these, social and chat apps are commonly rejected under 1.2.

## 1.3 Kids Category
Apps in the Kids category must not include third-party analytics or third-party advertising, with only narrow exceptions, and must not send personal information to third parties. Links out of the app and purchases need to be behind a parental gate.

## 2.5.1 Software Requirements
Apps may only use public APIs and must run on the currently shipping operating system. Private frameworks or undocumented APIs lead to rejection, often caught automatically.

## Replying to App Review
Reply in App Store Connect to the rejection message. Be polite and specific: say which guideline you addressed, what exactly you changed, and where the reviewer can see it, including the new build number if you uploaded one. If the reviewer could not log in, give a working demo account in App Review Information. If you believe the app was misunderstood, explain the feature step by step, with a screen recording if it helps. If the problem is only in App Store Connect metadata, such as a missing link, a screenshot or the description, fix it there and reply; no new build is needed. If you still disagree after replying, you can appeal to the App Review Board.
