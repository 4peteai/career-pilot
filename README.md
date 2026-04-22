# Career Pilot

AI-powered job search pipeline in Python. Scans job boards, parses LinkedIn alerts from Gmail, evaluates opportunities with Claude, generates tailored CVs, and tracks the application pipeline — all from the terminal.

Inspired by [career-ops](https://github.com/santifer/career-ops) by Santiago Fernandez; rewritten in Python with an English-only interface and Gmail IMAP as a LinkedIn workaround.

## Quick Start

```bash
git clone https://github.com/4peteai/career-pilot.git
cd career-pilot
pip install -e .
playwright install chromium

cp .env.example .env
cp config/profile.example.yml config/profile.yml
cp config/cv.example.md config/cv.md
cp config/portals.example.yml config/portals.yml
```

## License

MIT
