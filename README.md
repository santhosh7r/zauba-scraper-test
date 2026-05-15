# Zauba Scraper

Continuously scrapes the newest companies from [zaubacorp.com](https://www.zaubacorp.com)
and stores them in Supabase. Built to run unattended on a VPS forever — it
recovers from every error on its own.

## Quick start (VPS)

```bash
# 1. Get the code onto the VPS, then:
cd zauba_scraper
bash install.sh

# 2. Add your Supabase keys
nano .env

# 3. Start it — auto-restarts and starts on reboot
sudo cp zauba-scraper.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now zauba-scraper

# Watch it run
journalctl -u zauba-scraper -f
```

No root? Use the wrapper instead of systemd:

```bash
nohup ./run_forever.sh &
tail -f logs/scraper.log
```

## Test before running forever

```bash
./venv/bin/python3 bot.py --once    # one sweep, then exit
```

## Useful commands

| Action            | Command                                  |
|-------------------|-------------------------------------------|
| Status            | `systemctl status zauba-scraper`          |
| Live logs         | `journalctl -u zauba-scraper -f`          |
| Stop              | `sudo systemctl stop zauba-scraper`       |
| Restart           | `sudo systemctl restart zauba-scraper`    |

## How it works

See [DOCUMENTATION.md](DOCUMENTATION.md) for the full design. In short: it
sweeps ZaubaCorp's `age-A` bucket (the newest companies the site indexes),
scrapes every company, and upserts it to Supabase keyed by CIN. Read the data
newest-first with:

```sql
SELECT * FROM companies ORDER BY incorporation_date DESC NULLS LAST;
```
