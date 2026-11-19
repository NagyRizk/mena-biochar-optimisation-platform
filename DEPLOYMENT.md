# Deployment and secret management

- Set `GROQ_API_KEY` as a server-side environment variable or secret in the hosting provider.
- Set `GROQ_MODEL` only if a different Groq-supported model is intentionally selected.
- Never put the API key in client-side code, source control, notebook output, screenshots or downloadable configuration files.
- Enable HTTPS and authentication before sharing commercially sensitive scenarios.
- For production, pin dependency versions after a successful staging deployment and run the tests in CI.
- Streamlit Community Cloud can deploy directly from a Git repository; Docker is provided for managed container platforms.
