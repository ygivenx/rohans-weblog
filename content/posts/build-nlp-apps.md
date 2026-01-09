---
title: "Build NLP Apps, quickly!"
date: 2021-04-27
tags: ["data-science", "developer", "machine-learning", "nlp", "python", "streamlit"]
---

I created a demonstration application showcasing zero-shot text classification leveraging the HuggingFace library.

The application is a lightweight implementation using Streamlit that explores the zero-shot-classification pipeline provided by HuggingFace.

## Installation

The application runs in Docker with specific requirements:

- Docker memory must be configured to at least 6GB
- Pull the image: `docker pull ygivenx/zero-shot-app`
- Execute with port mapping: `docker run -it -p 8501:8501 ygivenx/zero-shot-app`
