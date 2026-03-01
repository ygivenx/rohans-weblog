# Design References

## Feed-first / Stream homepages

- **kottke.org** — The original tumblelog. Feed is the homepage. Mix of links, quotes, short posts, long essays. No categories in nav, just the stream.
- **simonwillison.net** — Developer blog where the homepage is a reverse-chron stream of everything (links, notes, TILs, posts). Great model for your stack.
- **macwright.com** — Minimal, feed-forward. Clean serif typography, no clutter. Posts + notes + links all on one stream.
- **manuelmoreale.com** — Extremely minimal. Feed is home. No sidebar, no tags visible on listing, just dates + titles.

## Long-form + microblog hybrid

- **aboutideasnow.com** — Minimal personal site, good example of mixing essay-length and short content.
- **beepb00p.xyz** — Dense but well-organized. Good reference for TIL/notes structure alongside posts.
- **gwern.net** — Opposite of minimal but the best reference for rich content taxonomy and linking between content types.
- **craigmod.com** — Beautiful typography, feed of essays + field reports + short notes. Great serif + whitespace model.

## Pure minimalism

- **paulgraham.com** — No nav chrome at all. Just a list of essays. Extreme simplicity.
- **patrickcollison.com** — Single page, sparse links. Reference for "less is more" nav.
- **danluu.com** — Pure text, no styling. Useful as a reminder that content > chrome.
- **sive.rs** (Derek Sivers) — Minimal nav, clear sections (Articles, Books, Now). Good reference for small nav taxonomy.

## Typography / visual

- **frankchimero.com** — Best-in-class typographic personal site. Serif, generous whitespace, no decoration.
- **robinrendle.com** — Designer's blog with excellent type choices. Newsletter + essays + notes.
- **paco.me** — Modern minimal, good reference if you want a slightly more designed feel.

## Key patterns to note

| Site | Homepage | Nav items | Typography |
|------|----------|-----------|------------|
| kottke.org | Stream | Archive, About | Georgia serif |
| simonwillison.net | Stream | Blog, TIL, Links, Projects | System sans |
| macwright.com | Feed | Notes, Work, About | Clean serif |
| manuelmoreale.com | Feed | Archive, About | Minimal serif |
| craigmod.com | Essays list | Essays, Ridgeline, About | Custom serif |
| sive.rs | Articles list | Articles, Books, Now, Contact | Simple sans |

## Recommendation for rohans-weblog

**Primary reference: simonwillison.net + macwright.com**

- Feed as homepage (stream of everything)
- Nav: Feed · Writing · TIL · Bookmarks · About
- Drop Search from nav (put it in footer or as icon)
- Keep Georgia serif, generous whitespace you already have
- Content types distinguished by small label (link / note / code) not by separate nav sections
