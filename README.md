# Kkabi Trading

Cryptocurrency trading bot & tools.

## Features

- Real-time market data monitoring
- Automated trading strategies
- Portfolio tracking & P&L analysis
- Risk management tools

## Tech Stack

- **Language**: Python 3.11+
- **Exchange API**: ccxt (multi-exchange support)
- **Data**: pandas, numpy
- **Visualization**: plotly

## Getting Started

```bash
# Clone
git clone https://github.com/JessicaArchive/kkabi-trading.git
cd kkabi-trading

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your API keys

# Run
python main.py
```

## Project Structure

```
kkabi-trading/
├── main.py              # Entry point
├── config.py            # Configuration loader
├── exchange/            # Exchange API wrappers
│   └── client.py
├── strategy/            # Trading strategies
│   └── base.py
├── utils/               # Utility functions
│   └── logger.py
├── requirements.txt
├── .env.example
└── .gitignore
```

## License

MIT
