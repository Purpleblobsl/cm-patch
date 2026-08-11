# CM-PATCH

**[C]ontract-[M]anagement - [P]atch [A]round [T]MF [C]ontract [H]andling**

`cm-patch` is a lightweight FIWARE Data Space Connector (**FDS**) component
designed to patch the gaps in the existing `contract-management` flow for
**central marketplaces**.

## Overview

When a contract is completed, `cm-patch`:

- Emits the appropriate TMF contract completion signals to the contract
  providers `contract-management`, components, if configured on the organization
  entity.
- Sends the corresponding request to the providers `contract-management`
  component through the **central marketplace**.

`cm-patch` does not manage the contract lifecycle itself. It simply handles the
missing completion and propagation steps required to keep the marketplace and
provider connectors in sync.

## Dev Setup

Using `uv` for local development:

```sh
# install python 3.14
uv python install 3.14

# create and activate a virtual environment
uv venv
. ./.venv/bin/activate

# install dependencies
uv sync

# verify version
python --version
```

### Certs

To get the `private-key.pem` in order to sing the **JWT** the application
creates, this is a fast way to fetch one from a connector:

```sh
NS="my-central-marketplace"

mkdir -p ./data/certs
kubectl -n "$NS" get secret did-secrets \
    -o jsonpath='{.data.private-key\.pem}' \
    | base64 -d \
    | tee ./data/certs/private-key.pem
```

## Local Development

Generating some `odrl-pap` policies, and supliying those to a target deployed
test connector, would be sublime, but it's **WIP**, so for now, just
`port-forward` the services:

```sh
NS="my-central-marketplace"

kubectl -n "$NS" port-forward \
    deployments/tm-forum-api-all-in-one 8081:8080 >/dev/null &
```

### Docker Compose

The application can be deployed locally using **Docker Compose**.

The Compose expects the holder private key at: `./data/certs/private-key.pem`

Create a `.env` file containing the required configuration and start the
application with:

```sh
docker compose up
```

## Notes

- This component was built to patch an error in the `contract-management`
  component where completion events were not emitted to the contract providers
  connectors.
- This component, is meant to work on the version `9.0.4` of the **FDS** chart

## Links

- [FIWARE Data Space Connector](https://github.com/FIWARE/data-space-connector)

