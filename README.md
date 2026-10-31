# Happy Hour Cocktails AI 🍸

An AI-assisted planning system for cocktail events — from understanding the event and choosing a menu to quantities, preparation, purchasing and cost comparison.

**Live demo:** https://happy-hour-ai-beta.vercel.app

No installation is required to try the live demo. The local setup below is intended for developers.

## What problem does it solve?

Planning a cocktail event usually means moving between recipes, spreadsheets, supplier websites and manual calculations.

Happy Hour Cocktails AI brings that workflow into one system:

- Define the event, guests, budget and preferences
- Get AI-assisted cocktail recommendations
- Calculate exact ingredient quantities
- Convert recipe requirements into whole purchasable packages
- Compare available products and retailers
- Replace missing or expensive products with alternatives
- Build a shopping plan
- Generate preparation and batching instructions
- Calculate equipment requirements
- Estimate the total event cost

## AI + deterministic engine

The system deliberately separates AI reasoning from business calculations.

The **LLM handles:**

- Understanding the event
- Asking useful planning questions
- Cocktail recommendations
- Planning guidance
- Natural-language interaction

The **deterministic Python engine handles:**

- Quantities
- Bottle/package rounding
- Ingredient allocation
- Product mappings
- Shopping quantities
- Costs
- Supplier comparisons

The LLM never calculates the final quantities or prices.

This keeps the numerical output reproducible and prevents AI hallucinations from changing event calculations.

## Architecture

### Frontend
- Next.js
- TypeScript
- React

### Backend
- FastAPI
- Python
- SQLAlchemy
- Alembic

### Data
- PostgreSQL
- Neon PostgreSQL for the hosted demo

### AI
- Groq / OpenAI-compatible LLM integration
- Tool-calling agent connected to deterministic backend functions
- AI usage is limited per user per day, enforced in the database

### Deployment
- Frontend: Vercel
- API: Render
- Database: Neon

## Accounts, workspaces and privacy

Every user signs up with email and password and automatically gets a private
**personal workspace**. Events — menus, quantities, shopping lists, purchase
plans, prep sheets, equipment, AI conversations — belong to a workspace and are
visible only to its members. The cocktail, ingredient, product and supplier
catalogue is shared by everyone.

- Isolation is enforced by the API, not the frontend. Every `/api/events/{event_id}/…`
  route depends on one ownership check (`app/core/auth.py → require_event_access`),
  and an event outside your workspace answers `404`, exactly like one that does not exist.
- Workspaces are `companies` rows reached through `company_memberships`, so several
  people can later share one company workspace without changing how events are scoped.
- Only platform admins can edit the shared catalogue (mappings and prices):
  `python scripts/set_admin.py --email you@example.com`.
- AI calls (event builder coach, event assistant) are limited per user per UTC day
  (`AI_DAILY_REQUEST_LIMIT`, default 10) with a global daily ceiling
  (`AI_GLOBAL_DAILY_REQUEST_LIMIT`). Counters live in PostgreSQL, so the limits hold
  across restarts and multiple API instances. Browsing and calculations never use AI quota.

## Public dataset

The repository includes a sanitized public dataset containing:

- 30 classic cocktails
- 54 ingredients
- 112 products
- 14 suppliers / retailers
- 102 supplier product listings

The dataset includes public product information and public retailer pricing snapshots.

Retailer prices may change. Always verify the current price and availability on the retailer website before purchasing.

Private business records, customers, historical events, private contacts and original private source spreadsheets are not included.

## Key product flows

### Event Builder

Create an event manually or with AI assistance.

The planner can capture:

- Guest count
- Budget
- Duration
- Event type
- Location
- Cocktail preferences
- Menu size

### Menu

Select cocktails and allocations for the event.

### Quantities

The calculation engine converts recipes into the exact amount required for the event and then into purchasable package quantities.

### Product alternatives

Each ingredient can be compared against other mapped products.

Alternatives are ranked using the **total cost for the event**, not simply the shelf price of one bottle.

### Buy & Compare

The shopping workflow combines event requirements with available retailer listings and purchase destinations.

### Prep

The system generates preparation and batching information based on the calculated event.

## Local development

### Requirements

- Git
- Docker Desktop

Clone the repository and create the backend environment file:

    cp .env.example backend/.env

Start the stack:

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

Never commit a real API key.

The repository contains `.env.example` with safe placeholder values.

## Reset the public database

Run:

    ./reset.sh

The public database is rebuilt from:

    backend/scripts/public_data/public_seed.json

## Testing

Backend (engine tests plus API-level auth, tenant-isolation and AI-quota tests):

    cd backend
    source venv/bin/activate
    pytest -q

The API tests use a throw-away SQLite database by default. To run them against
PostgreSQL, point `TEST_DATABASE_URL` at a **disposable** database (it is wiped):

    TEST_DATABASE_URL=postgresql+asyncpg://happyhour:happyhour@localhost:5432/happyhour_test pytest -q

Frontend production build:

    cd frontend
    npm run build

## API

Hosted API documentation:

https://happy-hour-ai.onrender.com/docs

Health endpoint:

https://happy-hour-ai.onrender.com/api/health

## Project principle

> AI should help make decisions — not invent the numbers.

Happy Hour Cocktails AI uses AI where language and recommendations are useful, while keeping quantities, pricing and purchasing logic deterministic.

## License

MIT License. See `LICENSE`.
