# Happy Hour AI 🍸

Plan a complete cocktail event with AI — from preferences and cocktail selection to quantities, preparation and shopping.

Happy Hour AI combines an AI-guided planning experience with a deterministic calculation engine. The AI helps understand the event and recommend cocktails; the backend handles quantities, product mappings and cost calculations.

## Built for

- HR & People teams
- Office managers
- Event planners
- Private hosts
- Bars and hospitality teams
- Anyone planning a cocktail event

## What it does

- Guided AI event creation
- Cocktail recommendations
- Ingredient quantity calculations
- Shopping lists
- Retailer and supplier comparison
- Cost estimates
- Preparation and batching instructions
- Equipment requirements
- Direct links to retailer product and search pages

## Architecture

- Next.js frontend
- FastAPI backend
- PostgreSQL database
- Docker Compose
- Alembic migrations

The LLM is used for guidance and recommendations.

Quantity and cost calculations are deterministic and are not performed by the LLM.

## Public dataset

The repository includes a sanitized public dataset with:

- 30 classic cocktails
- 54 ingredients
- 112 products
- 14 suppliers / retailers
- 102 supplier product listings

Retailer prices are a snapshot of publicly available pricing and may change. Verify current prices on the retailer website before purchasing.

Private business records, customer information and private source spreadsheets are not included.

## Quick start

Requirements:

- Git
- Docker Desktop

Run:

    cp .env.example backend/.env
    docker compose up --build -d

Then open:

- App: http://localhost:3000
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/api/health

## AI configuration

Edit:

    backend/.env

Example:

    LLM_PROVIDER=groq
    LLM_API_KEY=your_key_here

Supported providers:

- Groq
- Anthropic
- Gemini
- OpenRouter

Never commit a real API key.

## Reset the public database

Run:

    ./reset.sh

The database is rebuilt from:

    backend/scripts/public_data/public_seed.json

## Testing

Backend tests:

    cd backend
    source venv/bin/activate
    pytest -q

## License

MIT License. See `LICENSE`.
