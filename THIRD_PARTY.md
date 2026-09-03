# Third-party dependencies

Every open-source library this project installs, with its licence
(CodeSplash Guidelines 7.3).

Licences were read from each installed package's own metadata
(`importlib.metadata`: `License`, `License-Expression` and the `License ::`
classifiers), not from memory. To re-check after changing `requirements.txt`:

```bash
docker compose exec api python -c "from importlib.metadata import metadata, version; [print(n, version(n), metadata(n).get('License-Expression') or metadata(n).get('License') or [c for c in metadata(n).get_all('Classifier') or [] if c.startswith('License')]) for n in ['fastapi','uvicorn','pydantic','pydantic-settings','email-validator','sqlalchemy','alembic','psycopg','redis','pandas','numpy','pyyaml','lightgbm','passlib','argon2-cffi','PyJWT','slowapi','gunicorn','pytest','httpx','ruff']]"
```

## Runtime

| Package | Version | Licence | Project | Used for |
|---|---|---|---|---|
| FastAPI | 0.115.6 | MIT | <https://github.com/fastapi/fastapi> | The web framework and request validation |
| Uvicorn | 0.34.0 | BSD-3-Clause | <https://www.uvicorn.org/> | ASGI server, and the gunicorn worker class |
| Gunicorn | 23.0.0 | MIT | <https://gunicorn.org> | Process manager in production |
| Pydantic | 2.10.4 | MIT | <https://github.com/pydantic/pydantic> | Request and response schemas |
| pydantic-settings | 2.7.0 | MIT | <https://github.com/pydantic/pydantic-settings> | Reading settings from the environment |
| email-validator | 2.2.0 | Unlicense (public domain) | <https://github.com/JoshData/python-email-validator> | Validating the login email |
| SQLAlchemy | 2.0.36 | MIT | <https://www.sqlalchemy.org> | ORM and parameterised queries |
| Alembic | 1.14.0 | MIT | <https://alembic.sqlalchemy.org> | Database migrations |
| psycopg | 3.2.3 | **LGPL-3.0** | <https://psycopg.org/> | PostgreSQL driver |
| redis-py | 5.2.1 | MIT | <https://github.com/redis/redis-py> | Redis client (declared; caching not yet used) |
| pandas | 2.2.3 | BSD-3-Clause | <https://pandas.pydata.org> | Reading the dataset CSVs and building features |
| NumPy | 2.1.3 | BSD-3-Clause | <https://numpy.org> | Feature arithmetic, MAE/RMSE, SHAP aggregation |
| PyYAML | 6.0.2 | MIT | <https://pyyaml.org/> | Reading the three files in `config/` |
| LightGBM | 4.5.0 | MIT | <https://github.com/microsoft/LightGBM> | The visitor pressure model and its TreeSHAP values |
| passlib | 1.7.4 | BSD-2-Clause | <https://passlib.readthedocs.io> | argon2 password hashing |
| argon2-cffi | 25.1.0 | MIT | <https://github.com/hynek/argon2-cffi> | The argon2 implementation passlib calls |
| PyJWT | 2.10.1 | MIT | <https://github.com/jpadilla/pyjwt> | Signing and decoding the authority token |
| slowapi | 0.1.9 | MIT | <https://github.com/laurents/slowapi> | Per-client rate limiting |

## Development and test only

Not installed in a production image if the requirements are ever split.

| Package | Version | Licence | Project | Used for |
|---|---|---|---|---|
| pytest | 8.3.4 | MIT | <https://docs.pytest.org> | The test suite |
| HTTPX | 0.28.1 | BSD-3-Clause | <https://www.python-httpx.org> | The test client's transport |
| Ruff | 0.8.4 | MIT | <https://docs.astral.sh/ruff/> | Linting |

## Base images

| Image | Licence | Notes |
|---|---|---|
| `python:3.11-slim` | PSF for Python; Debian packages under their own licences | Base for the API image |
| `postgres:16` | PostgreSQL Licence (permissive, BSD-like) | Database |
| `redis:7` | RSALv2 / SSPLv1 from Redis 7.4 | Used as a stock image, unmodified and not redistributed |
| `libgomp1` | GPL-3.0 with the GCC Runtime Library Exception | Installed in the API image; LightGBM needs OpenMP |

## Data sources

Licences and terms for SLTDA, Open-Meteo and OpenAQ are recorded in
`ml/data/README.md` alongside what was taken from each.

## Note on psycopg

**psycopg 3 is LGPL-3.0, the only copyleft licence in the runtime list.** It is
used as an unmodified library imported at runtime, which LGPL permits without
any obligation on this project's own code. It would only become a problem if
psycopg's source were modified, or if it were statically linked into a
distributed binary. Neither is the case: it arrives as a normal pip package
inside the image. Worth knowing, because "did you check the licences?" is a
fair question and "they were all MIT" would be the wrong answer.

`libgomp1` is GPL-3.0 but carries the GCC Runtime Library Exception, which
exists precisely so that linking against it does not impose the GPL on the
program using it.
