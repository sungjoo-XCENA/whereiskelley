# Wine-Searcher browser collector

This Chrome extension collects public merchant profile metadata into the existing Where is Kelley SQLite database. It uses a normal user-controlled Chrome tab. It does not solve or automate human-verification challenges.

## Install

1. Start the Where is Kelley server with `WHEREISKELLEY_ADMIN_PASSWORD` configured.
2. Open `chrome://extensions` in Chrome.
3. Turn on **Developer mode**.
4. Choose **Load unpacked** and select this directory.
5. Open the extension, enter the server address and the same admin password, and test a small ID range.

If Wine-Searcher displays a press-and-hold verification screen, complete it manually in the collector tab. Then open the extension and choose **Resume after verification**.

The password remains in Chrome session storage only. The server receives an expiring HMAC signature, not the password itself.
