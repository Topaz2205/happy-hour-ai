# Happy Hour AI — Developer Setup

This guide is for developers who want to run Happy Hour AI locally.

End users do not need Docker, Git or an API key. They use the hosted web application.

## Requirements

- Git
- Docker Desktop

Make sure Docker Desktop is running.

## Start locally

From the project root:

    cp .env.example backend/.env
    docker compose up --build -d

Or run:

    ./setup.sh

## Open

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

## Public data

On startup, the backend runs database migrations and loads:

    backend/scripts/public_data/public_seed.json

The public dataset contains classic cocktails, ingredients, products and public retailer listings.

Private business spreadsheets, customer data and historical business records are not included.

## Reset database

    ./reset.sh

## Useful commands

Check containers:

    docker compose ps

Backend logs:

    docker compose logs backend --tail=100

Stop:

    docker compose down

Rebuild:

    docker compose up --build -d
