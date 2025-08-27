# Watsonx Auth App

Aplicación Flask para autenticación con Microsoft (Azure Entra ID) antes de acceder al agente de Watsonx Orchestrate.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate  # en Windows usar .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env