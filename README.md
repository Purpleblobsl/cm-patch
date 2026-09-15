# CM-PATCH

**[C]ontract-[M]anagement - [P]atch [A]round [T]MF [C]ontract [H]andling**

`cm-patch` is a lightweight FIWARE Data Space Connector (**FDS**) component
designed to replace the missing/broken/missconfigured order-event functionality
in the existing `contract-management` flow for **central marketplaces**.

Instead of simply propagating contract/order events, `cm-patch` receives order
start/stop signals from the central marketplace and dispatches them to the
configured provider `cm-patch` components. The provider components then apply
the required configuration changes to their local `odrl-pap` and `til`
components.

This allows contract completion and termination to result in actual changes to
the provider connector configuration.

## Overview

When the `tmf-api` emits product order event, `cm-patch`:

- Receives the order event.
- Resolves the organizations and providers involved in the order.
- Determines which providers have `cm-patch` configured.
- Generates the required **OID4VP** access token for each provider.
- Sends an authenticated order **start** or **stop** signal to the provider's
  `cm-patch` component.
- The provider `cm-patch` component applies the corresponding configuration
  changes to its **ODRL-PAP** and **TIL** components.

`cm-patch` does not manage the order lifecycle itself. It simply handles the
missing completion and propagation steps required to keep the marketplace and
provider connectors in sync.

```
 [provider]          gen JWT    )      ( [central-marketplace]
                 .-------------------. (
   .----------.  |       .--------.  | (
   | verifier |<-+-------| apisix |<-+ (
   '----------'    verify'--------'  | (
 in?|^ |^ |^creds?            | )    | (
    || || |'---------.        | )    | (
    || || '---------.|        | )    | (
    || |'----.pass? ||        | )    | (
    v| '----v|      v|        | )    | (
   .-----. .-----. .-----.    | )    | (
   | til | | pap | | ccs |    | )    | (      .---------.
   '-----' '-----' '-----'    | )    | (      | tmf-api |
      ^|     ^|               | )    | (      '---------'
update||     ||update         | )    | (    Event| ^|resolve ids
      |v     |v               | )    | (         v |v
     .----------. /order/x    | )    | (      .----------.
     | cm-patch |<------------' )    '--------| cm-patch |
     '----------' .-------------------------. '----------'
              '---' ok?         )      (    '---^
                                )      (
```

### Project structure

```
cm-patch/
|-- src/
|   |-- config.py             # app config
|   |-- deserializer.py       # request generic deserializer
|   |-- dispatcher.py         # dispatch order signals to cm-patch/odrl-pap/til
|   |-- http.py               # enpoints
|   |-- jwt.py                # creds
|   |-- models.py             # response models
|   |-- queue.py              # job queues (TODO)
|   |-- request.py            # request utils
|   |-- resolver.py           # from the event resolve the provider organization
|   '-- utils.py              # utils
|-- data/
|   |-- certs/                # certificates to sing JWT tokens
|   |   '-- private-key.pem
|   '-- queue/                # backup queues
|       |-- event/            # - received events to be resolved
|       '-- contract/         # - resolved contract to be dispatched
|-- README.md
'-- main.py                   # entrypoint
```

### Event handling flow

The service receives the order event and only processes events that represent a
relevant order state change.

```
   .---------------.
   |    http.py    |
   |---------------|
   | receive event |
   | deserialize   | no (204 No Content, skip)
   | is_completed? |---X
   '---------------'
          | yes (204 No Content, push)
          V
   .---------------.
  (   eventQueue    )<-.
   `---------------'   |
          | (head)     |
          V            |
   .---------------.   |
   |  resolver.py  |   |
   |---------------|   |
   | PrOrder       |   |
   | PrOffering    |   |
   | PrSpec        |   |
   | Organization  |   | no (pop)
   | has_cm_url?   |---'
   '---------------'
          | yes (push)
          V
   .---------------.
  (  contractQueue  )<-.
   `---------------'   |
          | (head)     |
          V            |
   .---------------.   |
   | dispatcher.py |   |
   |---------------|   |
   | create JWT    |   | ok (pop)
   | POST cm-patch |---'
   '---------------'
          | error (skip)
          X
```

> **Note**:
> The queue system is currently **WIP**. If an error occurs while processing an
> event, the event may be dropped and not retried. As a result, healthy events
> may be lost.

The provider `cm-patch` then receives the order signal:

```
   .---------------.
   |    http.py    |    .---------------.
   |---------------|    |  dispatch.py  |
   | receive order |ok  |---------------|
   | deserialize   |--->| is_completed? |
   '---------------'    '---------------'
          |error           | ^     | ^ get/post/delete
          x                | |     | |
                           v |     v |
                         .-----. .-----.
                         | pap | | til |
                         '-----' '-----'
```

## Dev Setup

Using `uv` for local development:

```sh
# install python 3.14
uv python install 3.14

# install dependencies & create virtual environment
uv sync
. ./.venv/bin/activate

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
NS_CM="my-central-marketplace"
NS_P="my-provider"

kubectl -n "$NS_CM" port-forward --address 0.0.0.0 \
    deployments/tm-forum-api-all-in-one 8081:8080 >/dev/null &

kubectl port-forward -n "$NS_P" --address 0.0.0.0\
  deployments/odrl-pap 8082:8080 >/dev/null &
kubectl port-forward -n "$NS_P" --address 0.0.0.0\
  deployments/trusted-issuers-list 8083:8080 >/dev/null &
```

> **Note**:
> The `--address 0.0.0.0` is so the containers on the docker compose can reach
> your `localhost`.

### Docker Compose

The application can be deployed locally using **Docker Compose**.

The Compose expects the holder private key at: `./data/certs/private-key.pem`

Create a `.env` file containing the required configuration and start the
application with:

```sh
docker compose up
```

## Notes

**Limitations**:

- This component, is meant to work on the version `9.0.4` of the **FDS** chart
- The `cm-patch`, only issues JWT when dispatching to another `cm-patch`,
  meaning, the `pap` and `til` must be local.

## Links

- [FIWARE Data Space Connector](https://github.com/FIWARE/data-space-connector)
