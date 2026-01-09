---
title: "The YAML Syntax – get over the config files"
date: 2022-09-13
tags: ["developer", "data-science", "productivity", "yaml"]
---

A quick reference guide for understanding YAML syntax, covering the fundamental structures used in configuration files.

## Lists

Lists in YAML begin each item on the same indentation level with a dash and space prefix:

```yaml
# a list of models
- logreg
- randomforest
- xgboost
- mlp
```

## Dictionaries

Dictionary entries use key-value pairs separated by a colon and space:

```yaml
rohan:
  name: Rohan Singh
  job: Data Scientist III
  skill: Elite
```

## Complex Data Structures

Lists of dictionaries combine both concepts:

```yaml
- rohan:
      name: Rohan Singh
      job: Geneticist
      skill: Beginner
- emmanuelle:
      name: Emmanuelle Charpentier
      job: Professor and Researcher
      skill: Elite
```

## Flow Connections

Abbreviated representations use inline syntax:

```yaml
rohan: {name: Rohan Singh, job: Data Scientist III, skill: Elite}
```

## Boolean Values

Use lowercase `true/false` for yamllint compatibility. Quote literal values like `"yes"` or `"no"` to preserve them as strings.

## Multiline Values

**Literal Block Scalar (`|`):** Preserves newlines and trailing spaces exactly as written.

**Folded Block Scalar (`>`):** Converts newlines to spaces for improved readability of lengthy values.

Alternatively, use the `\n` escape character within quoted strings.

## Common Gotchas

The characters `:` (mapping indicator) and `#` (comment starter) require careful handling. Problematic examples include unquoted colons within values. Solutions include using single or double quotes, though escape sequences only work within double quotes.
