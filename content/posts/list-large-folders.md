---
title: "List all folders over a GB in terminal"
date: 2021-04-26
tags: ["developer", "productivity", "terminal"]
---

Several times, you realize that you need to see folders with a lot of data in them.

This command is really useful to see all the large folders lying around in the current directory:

```bash
du -h . | grep '[0-9\.]\+G'
```

Or to find folders over 1GB specifically:

```bash
du -h -d 1 . 2>/dev/null | awk '$1 ~ /G/ && $1+0 >= 1'
```
