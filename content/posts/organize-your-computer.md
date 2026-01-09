---
title: "Organize your computer"
date: 2021-04-29
tags: ["developer", "productivity", "python"]
---

If you use **Python** and want a **tidy computer** – this piece is for you.

Your files scattered across downloads, desktop, and elsewhere on your Mac. A Python utility called `organize-tool` helps declutter and systematize everything using straightforward YAML setup.

The **standout feature**: you can embed Python code directly in actions.

Props to [tfeldmann](https://github.com/tfeldmann) for creating this impressive utility.

**Installation:** `pip3 install -U organize-tool`

- [GitHub](https://github.com/tfeldmann/organize)
- [Docs](https://organize.readthedocs.io/en/latest/)

## Usage

![organize-tool screenshot](/images/organize-tool-screenshot.png)

```yaml
rules:
    # move files to folder according to extension
    - folders:
        - ~/Downloads/**/*
        - ~/Desktop/**/*
      filters:
        - extension:
          - pdf
          - docx
          - jpg
          - pptx
          - xlsx
          - mov
          - mp4
          - m4a
          - png
          - heic
          - csv
          - jpeg
          - json
          - key
          - zip
      actions:
        - move: ~/Documents/{extension.upper}/
    # Move screenshots to a dir
    - folders: ~/Desktop
      filters:
        - filename:
            startswith: "Screen Shot"
      actions:
        - move: ~/Desktop/Screenshots/
    # remove empty files
    - folders:
          - ~/Downloads
          - ~/Desktop
      filters:
          - filesize: 0
      actions:
          - trash
    # remove partial downloads
    - folders: ~/Downloads
      filters:
          - extension:
                - download
                - crdownload
                - part
                - dmg
          - lastmodified:
                days: 2
                mode: older
      actions:
          - trash
    # remove duplicate files
    - folders:
        - ~/Desktop
        - ~/Downloads
        - ~/Documents
      subfolders: true
      filters:
        - duplicate
      actions:
        - echo: "{path} is a duplicate of {duplicate}"
        - trash
```
