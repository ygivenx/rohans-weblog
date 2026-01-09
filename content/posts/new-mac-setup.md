---
title: "So, you got a new Mac"
date: 2021-04-26
tags: ["data-science", "developer", "mac", "setup"]
---

A setup guide for configuring a new MacBook for data science work.

## Initial Setup

Begin by installing Xcode command-line tools:

```bash
xcode-select --install
```

## Package Installation

Essential utilities include Homebrew package manager, oh-my-zsh shell framework, and Git with LFS support.

Enable plugins for git, aliases, and Python in oh-my-zsh.

Additional CLI tools:
- **pyenv** - managing Python versions
- **tldr** - command documentation
- **httpie** - curl alternative
- **amethyst** - window management
- **iTerm** - terminal replacement

## Python Configuration

Install Python 3.12 via pyenv and set it as the global version:

```bash
pyenv install 3.12
pyenv global 3.12
```

## Development Tools

Docker installation is recommended, with a note to increase memory allocation for data science images.

## Applications

Key applications:
- **1Password** - password management
- **VS Code** - configured with command-line access

## Pro Tip

Install python using this command if you get errors with running and loading libs:

```bash
PYTHON_CONFIGURE_OPTS="--enable-framework" pyenv install 3.9.0
```
