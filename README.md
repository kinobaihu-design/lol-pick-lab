# LoL Pick Lab

A free website that ranks League of Legends ADC and support champions every patch, using personal scoring rules on Diamond+ match data from the official Riot Games API.

**Planned features**

1. A personal tier list for ADC (support later)
2. Build recommendations: items, runes and skill order
3. A draft helper that recommends a pick

**Status:** the data collector runs on GitHub Actions every 6 hours. The data is on the `data` branch. The website isn't built yet.

Runs on free services: the Riot API (personal key), GitHub Actions for the daily data collection, and Vercel for the website. The Riot API key is stored as a GitHub secret and is never in the code.

*LoL Pick Lab isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. League of Legends and Riot Games are trademarks or registered trademarks of Riot Games, Inc.*
