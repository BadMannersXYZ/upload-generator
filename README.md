# upload-generator

Script to generate multi-gallery upload-ready files.

## Requirements

- A Python environment to install dependencies (`pip install -r requirements.txt`); if unsure, create a fresh one with `virtualenv venv`.
- LibreOffice 6.0+, making sure that `libreoffice` is in your PATH.

## Usage

Run with `python main.py -h` for options. Generated files are output to `./out` by default.

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

Uppercase letters are optional. Only include your username for websites that you wish to generate descriptions for.

Input descriptions should be formatted as BBCode. The following tags are accepted:

```bbcode
[b]Bold text[/b]
[i]Italic text[/i]
[url=https://github.com]URL link[/url]
```

There are also special tags to link to yourself or other users automatically. This may include websites not available in the configuration:

```bbcode
[self][/self]

[eka]EkasPortalUser[/eka]
[fa]FurAffinityUser[/fa]
[weasyl]WeasylUser[/weasyl]
[ib]InkbunnyUser[/ib]
[sf]SoFurryUser[/sf]
[twitter]@TwitterUser[/twitter] - Leading '@' is optional
[mastodon]@MastodonUser@mastodoninstance.com[/mastodon] - Leading '@' is optional
```

`[self][/self]` tags must always be empty. The other tags are nestable and flexible, allowing attributes to display information differently on each supported website. Some examples:

```bbcode
[eka=Lorem][/eka] is equivalent to [eka]Lorem[/eka].

[fa=Ipsum]Dolor[/fa] shows Ipsum's username on FurAffinity, and Dolor everywhere else as a link to Ipsum's FA userpage.

[weasyl=Sit][ib=Amet][/ib][/weasyl] will show the two user links on Weasyl and Inkbunny as expected. For other websites, the innermost tag is prioritized - Inkbunny, in this case.
[ib=Amet][weasyl=Sit][/weasyl][/ib] is the same as above, but the Weasyl link is prioritized instead.

[ib=Amet][weasyl=Sit]Consectetur[/weasyl][/ib] is the same as above, but Consectetur is displayed as the username for websites other than Inkbunny and Weasyl, with a link to the Weasyl gallery.

[generic=https://github.com/BadMannersXYZ]Bad Manners[/generic] can be used as the innermost tag with a mandatory URL attribute and default username, and is similar to the URL tag, but it can be nested within other profile links. Those other profile links get used only at their respective websites.
```

Another special set of tags is `[if][/if]` and `[else][/else]`. The if tag receives a parameter for the condition (i.e. `[if=parameter==value]...[/if]` or `[if=parameter!=value]...[/if]`) to check on the current transformer, and lets you show or omit generated content respectively. The else tag is optional but must appear immediately after an if tag (no whitespace in-between), and displays whenever the condition is false instead. For now, the if tag only accepts the `site` parameter (eg. `[if=site==fa]...[/if][else]...[/else]` or `[if=site!=furaffinity]...[/if]`).
