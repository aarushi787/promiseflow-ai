# Supabase database certificate

Public CA certificate downloaded from the selected project's Database Settings → SSL configuration on 7 September 2026:
https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt

This file is a public trust certificate, not a private key. Set `PROMISEFLOW_DB_SSLROOTCERT=backend/certs/supabase-ca.crt` in deployments using this Supabase certificate. Keep `sslmode=verify-full` enabled. Replace the certificate using the official project settings when Supabase rotates its CA.
