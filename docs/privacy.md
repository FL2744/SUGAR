# Privacy and data handling

What SUGAR keeps, where it goes, and what it never does. Written for the people running it and the people reviewing it.

## What stays on your computer

- **Projects** (plans, collected posts, reviews, comments, institution records, exports) live in a folder on your machine (desktop) or on the server that runs SUGAR (hosted). Nothing is uploaded to the SUGAR project or its authors.
- **Credentials** (AI provider keys, platform tokens) are kept in the operating system's credential vault, or in environment variables on a server. They are never written into projects, exports, profiles, handoff bundles or logs.
- **Review and author names** are what a person types as their name, or their member address on a hosted server. They are stored in the project's review log so a verification can be attributed.

## What leaves your computer, and only when you use it

| Feature | Goes to | What is sent |
| --- | --- | --- |
| Collecting from a platform or open source | That platform (Bluesky, Mastodon, Wikipedia, GDELT, OpenAlex, feeds, websites) | The search terms or addresses in your plan |
| Reading a website | The site, after checking robots.txt, one request per second | A normal page request |
| Page history | The Internet Archive | The page address |
| AI features (interpretation, translation, coding) | The provider you chose (OpenAI or Virginia Tech ARC), never a silent fallback | The text being processed and your instructions. Choose "No AI" to send nothing |
| Geocoding a place | Nominatim (OpenStreetMap) | The place name |
| The map | OpenFreeMap and, for Terrain, OpenTopoMap | The area being viewed (tile requests) |
| Checking for updates | GitHub | A request for this project's public release list. No project data, no account, no identifier beyond the app version |
| Downloading an update | GitHub's release hosts | A download request; the file is checked against its published checksum |

There is no analytics, tracking, advertising or crash reporting. "Check for updates when SUGAR opens" can be turned off in Settings → Updates.

## Public information, handled carefully

SUGAR works with publicly available posts and pages. It records where each item came from, keeps the original and any translation, and marks what a person has verified. It does not log in to accounts that are not yours, bypass access controls, or collect private messages. Posts name real people: treat exports accordingly, share them only as your organization's rules allow, and follow platform terms. Place and country tags are inferred or approximate and are labeled so.

## Controls

- Delete a project folder to delete its data. Revoke a member's access in Settings (hosted).
- Handoff bundles and exports contain only what you export; they contain no credentials.
- Method profiles contain no credentials and no collected posts by default.

## Before wider use

This describes the software's behavior, not an organization's legal review. A deployment for a government office should have its own review of data retention, the platforms' terms, and any records or privacy rules that apply to it.
