# upload-generator

Script to generate multi-gallery upload-ready files.

## Requirements

- A Python environment to install dependencies (`pip install -r requirements.txt`); if unsure, create a fresh one with `virtualenv venv`.
- LibreOffice 6.0+, making sure that `libreoffice` is in your PATH.

## Installation

I recommend creating a virtualenv first. Linux/macOS/Unix example:

```sh
virtualenv venv
source venv/bin/activate  # Also run every time you use this tool
pip install -r requirements.txt
activate-global-python-argcomplete
```

Windows example (autocompletion is not available):

```powershell
virtualenv venv
.\venv\Scripts\activate  # Also run every time you use this tool
pip install -r requirements.txt
```

## Usage

Run with `python main.py -h` (or simply `./main.py -h`) for options. Generated files are output to `./out` by default.

### Story files

When generating an .RTF file from the source text, the script expects that LibreOffice's style has "Preformatted Text" for plaintext, and "Normal" as the intended style to replace it with. Unless you've tinkered with LibreOffice's default formatting, this won't be an issue.

### Description files

In order to parse descriptions, you need a configuration file (default path is `./config.json`) with the websites you wish to upload to, and your username there. For example:

```json
{
  "aryion": "MyUsername",
  "furaffinity": "My_Username",
  "inkbunny": "MyUsername",
  "sofurry": "My Username",
  "weasyl": "MyUsername"
}
```

Uppercase letters for usernames are optional. Only include your username for websites that you wish to generate descriptions/stories for.

#### Basic formatting

Input descriptions should be formatted as BBCode. The following tags are accepted:

```bbcode
[b]Bold text[/b]
[i]Italic text[/i]
[u]Underline text[/u]
[url=https://github.com/BadMannersXYZ]URL link[/url]
```

#### Self-link formatting

`[self][/self]` will create a link to yourself for each website, with the same formatting as the `[user]...[/user]` switch. The inside of this tag must be always empty.

#### Conditional formatting

Another special set of tags is `[if=...][/if]` or `[if=...][/if][else][/else]`. The `if` tag lets you conditionally show content . The `else` tag is optional but must appear immediately after an `if` tag (no whitespace in-between), and displays whenever the condition is false instead.

The following parameters are available:

- `site`: generated according to the target website, eg. `[if=site==fa]...[/if]` or `[if=site!=furaffinity]...[/if][else]...[/else]`
- `define`: generated according to argument(s) defined to the script into the command line (i.e. with the `-D / --define-option` flag), eg. `[if=define==prod]...[/if][else]...[/else]` or `[if=define in possible_flag_1,possible_flag_2]...[/if][else]...[/else]`

The following conditions are available:

- `==`: eg. `[if=site==eka]Only show this on Eka's Portal.[/if][else]Show this everywhere except Eka's Portal![/else]`
- `!=`: eg. `[if=site!=eka]Show this everywhere except Eka's Portal![/if]`
- ` in `: eg. `[if=site in eka,fa]Only show this on Eka's Portal or Fur Affinity...[/if]`

#### Switch formatting

You can use special switch tags, which will generate different information per website automatically. There are two options available: creating different URLs per website, or linking to different users.

```bbcode
Available for both [user]...[/user] and [siteurl]...[/siteurl] tags
- [generic=https://example.com/GenericUser]Generic text to display[/generic]
- [eka=EkasPortalUser][/eka] [aryion=EkasPortalUser][/aryion]
- [fa=FurAffinityUser][/fa] [furaffinity=FurAffinityUser][/furaffinity]
- [weasyl=WeasylUser][/weasyl]
- [ib=InkbunnyUser][/ib] [inkbunnny=InkbunnyUser][/inkbunnny]
- [sf=SoFurryUser][/sf] [sofurry=SoFurryUser][/sofurry]

Available only for [user]...[/user]
- [twitter=@TwitterUser][/twitter] - Leading '@' is optional
- [mastodon=@MastodonUser@mastodoninstance.com][/mastodon] - Leading '@' is optional
```

These tags are nestable and flexible, requiring attributes to display information differently on each supported website. Some examples:

```bbcode
[user][eka]Lorem[/eka][/user] is equivalent to [user][eka=Lorem][/eka][/user].

[user][fa=Ipsum]Dolor[/fa][/user] shows Ipsum's username on Fur Affinity, and "Dolor" everywhere else with a link to Ipsum's userpage on FA.

[user][ib=Sit][weasyl=Amet][twitter=Consectetur][/twitter][/weasyl][/ib][/user] will show a different usernames on Inkbunny and Weasyl. For other websites, the innermost user name and link are prioritized - Twitter, in this case.
[user][ib=Sit][twitter=Consectetur][weasyl=Amet][/weasyl][/twitter][/ib][/user] is similar, but the Weasyl user data is prioritized for websites other than Inkbunny. In this case, the Twitter tag is rendered useless, since descriptions can't be generated for the website.

[siteurl][sf=https://a.com][eka=https://b.com]Adipiscing[/eka][/sf][/siteurl] displays links on SoFurry and Eka's Portal, with "Adipiscing" as the link's text. Other websites won't display any link.
[siteurl][sf=https://a.com][eka=https://b.com][generic=https://c.com]Adipiscing[/generic][/eka][/sf][/siteurl] is the same as above, but with the innermost generic tag serving as a fallback, guaranteeing that a link will be generated for all websites.

[user][fa=Elit][generic=https://github.com/BadMannersXYZ]Bad Manners[/generic][/fa][/user] shows how a generic tag can be used for user links as well, displayed everywhere aside from Fur Affinity in this example. User tags don't need an explicit fallback - the innermost tag is always used as a fallback for user links.
```
