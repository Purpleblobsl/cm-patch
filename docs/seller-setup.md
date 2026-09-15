# Seller Setup

For a `cm-patch` service to emit the `/order/start` and `/order/stop` events to
the respective seller organizations after a product order is completed, the
seller's connector needs to be configured to use the `cm-patch` service.

The required configuration is relatively small and consists of a few changes to
the seller connector.

> **Note**:
> The configuration can generally be applied either by modifying the values of
> the corresponding deployment or by updating the respective components through
> their APIs.

## Credentials Configuration Service

Configure the `MarketplaceCredential` required by `cm-patch`:

```yaml
services:
- id: cm-patch
  defaultOidcScope: "external-marketplace"
  authorizationType: "DEEPLINK"
  oidcScopes:
    "external-marketplace":
      credentials:
      - type: MarketplaceCredential
        trustedParticipantsLists: ["https://tir.trust.com"]
        trustedIssuersLists: ["*"]
        jwtInclusion:
          enabled: true
          fullInclusion: true
      presentationDefinition:
        id: marketplace-pd
        input_descriptors:
        - id: marketplace-query
          constraints:
            fields:
            - id: type
              path: ["$.type"]
              filter:
                type: array
                contains:
                  const: "MarketplaceCredential"
          format:
            jwt_vc_json:
              alg: ["ES256"]
```

> **Note**:
> This can also be configured by sending a `POST` request to the `css`

## Trusted Issuers Lists

The connectors needs to register the `cm-patch` connector that want's to receive
order events from.

So it would need to add a `MarketplaceCredential` to the registry:

```sh
SELLER_TIL_URL="http://trusted-issuers-lists:8080"
CM_DID="did:xxx:yyyyy"

curl -siL -X POST "${SELLER_TIL_URL}/issuer" \
  -H 'Content-Type: application/json' \
  -d '{
  "did": "'"$CM_DID"'",
  "credentials": [ { "credentialsType": "MarketplaceCredential" } ]
}'
```

## pap

The policy can be applied to the default set of policies:

```sh
PAP_URL="http://odrl-pap:8080"

curl -si -X POST "${PAP_URL}/policy" \
    -H 'Content-Type: application/json' \
    -d '{
  "@context": { "odrl": "http://www.w3.org/ns/odrl/2/" },
  "@id": "https://www.mp-operation.org/policy/common/cm-patch/use/order",
  "odrl:uid": "https://www.mp-operation.org/policy/common/cm-patch/use/order",
  "@type": "odrl:Policy",
  "odrl:permission": {
    "odrl:assigner": { "@id": "https://www.mp-operation.org/" },
    "odrl:target": {
      "@type": "odrl:AssetCollection",
      "odrl:source": "urn:asset",
      "odrl:refinement": [
        {
          "@type": "odrl:Constraint",
          "odrl:leftOperand":  { "@id": "http:path" },
          "odrl:operator":     { "@id": "http:isInPath" },
          "odrl:rightOperand": { "@id": "/order" }
        }
      ]
    },
    "odrl:assignee": {
      "@type": "odrl:PartyCollection",
      "odrl:source": "urn:user",
      "odrl:refinement": {
        "@type": "odrl:Constraint",
        "odrl:leftOperand":  { "@id": "vc:type" },
        "odrl:operator":     { "@id": "odrl:hasPart" },
        "odrl:rightOperand": { "@id": "MarketplaceCredential" }
      }
    },
    "odrl:action": { "@id": "odrl:use" }
  }
}'
```

### Scoped Policy

The best way to setup your policies would be to scope them to the service they
are meant to work with.

First register the service:

```sh
PAP_URL="http://odrl-pap:8080"

curl -s -X POST "${PAP_URL}/service" \
  -H 'Content-Type: application/json' \
  -d '{ "id": "cm-patch" }' \
  | jq .
```

It would return something like this:

```json
{
  "policyPath": "ffffffffff/main"
}
```

No add the policy to the scope:

```sh
PAP_URL="http://odrl-pap:8080"

curl -s -X POST "${PAP_URL}/service/cm-patch/policy" \
    -H 'Content-Type: application/json' \
    -d '{...}'
```

Now you need the `policyPath`, its a bit counter intuitive but the abaible
services are queried, the thing we wan't is not directly given to us:

```sh
curl -s "${PAP_URL}/service" | jq .
```

Returns:

```json
[
  {
    "id": "cm-patch",
    "policyPath": "cm-patch/main" <-- this is a lie
  }
]
```

The real path is stored in each scoped service:


```sh
curl -s "${PAP_URL}/service/cm-patch" | jq .
```

Returns:

```json
{
  "id": "cm-patch",
  "policyPath": "ffffffffff/main",  <-- this is the good one
  "policies": [ ... ]
}
```

This `policyPath` needs to be setup at the `apisix` services.

> **Note**:
> As long as I now, the scoped services only get applied te policies from that
> scope, so the default scope is not a global one, but anther scope that non
> configured services fall into.

> **Tick**:
>
> A quick way to get the desired `policyPath` from a service would be the next
> `jq` query
>
> ```sh
> PAP_URL="http://odrl-pap:8080"
> SERVICE="cm-patch"
> curl -s "${PAP_URL}/service/${SERVICE}" | jq -r '.policyPath'
> ```

## TMF config

> **Note**:
> The following changes should be applied to the external connector used by the
> seller to do it's bussine `( -#-#)`, such as a _central marketplace_.

> **Note**:
> The seller connector must already be registered in the _external connectors_
> `til` and be able to authenticate with the **markeplace**.
>
> > **Note**:
> > From a purely technical perspective, the marketplace is not required. All
> > operations can be performed directly through the `tmf-api` using terminal
> > `curl` commands. `d(-[0]~[0]- )`

A typical organization registered in the TMF API looks like this:

```json
{
  "id": "urn:ngsi-ld:organization:ffffffff-ffff-ffff-ffff-ffffffffffff",
  "href": "urn:ngsi-ld:organization:ffffffff-ffff-ffff-ffff-ffffffffffff",
  "tradingName": "did:xxx:yyyyy",
  "externalReference": [
    {
      "externalReferenceType": "idm_id",
      "name": "did:xxx:yyyyy"
    }
  ]
}
```

The organization must then be updated with the metadata required by `cm-patch`.
`PATCH` the desired organization as follows:

```sh
ORG_ID="urn:ngsi-ld:organization:ffffffff-ffff-ffff-ffff-ffffffffffff"
ORG_DID="did:xxx:yyyyy"
ORG_CMPATCH_URL="https://cm-patch.seller.com"

TMF_URL="http:/tm-forum-api-svc:8080"

curl -siX PATCH "$TMF_URL/tmf-api/party/v4/organization/$ORG_ID" \
    -H 'Content-Type: application/json;charset=utf-8' \
    -d '{
  "partyCharacteristic": [
    { "name": "did", "value": "'"${ORG_DID}"'" },
    {
        "name": "cmPatch",
        "value": {
            "address": "'"${ORG_CMPATCH_URL}"'",
            "clientId": "cm-patch",
            "scope": ["external-marketplace"]
        }
    }
  ]
}'
```

> **Note**:
> The `scope` should match the one configured on the `ccs`.

> **Note**:
> The `clientId` is not used, but just let it be.

> **Note**:
> Instead of patching an existing organization, a new organization can be
> created with the required `partyCharacteristic` values already configured.

## Apisix

The `apisix` configuration can be updated through its API, but for this setup it
is recommended to configure it through the deployment values instead. This keeps
the configuration declarative and ensures it is preserved across deployments.

The following snippet can be used in the `apisix` deployment's `values.yaml`:

```yaml
routes:
- uri: /.well-known/openid-configuration
  host: &cmpHost cm-patch.seller.com
  upstream: &verifierUpstream
    nodes:
      verifier:3000: 1
    type: roundrobin
  plugins:
    proxy-rewrite:
      uri: /services/cm-patch/.well-known/openid-configuration
- uri: /*
  host: *cmpHost
  priority: 100
  vars:
    - ["uri", "~~", "/\\.well-known/openid-configuration$"]
  upstream: *verifierUpstream
  plugins:
    proxy-rewrite:
      uri: /services/cm-patch/.well-known/openid-configuration
- uri: /*
  host: *cmpHost
  upstream:
    nodes:
      cm-patch:8080: 1
    type: roundrobin
  plugins:
    openid-connect:
      bearer_only: true
      use_jwks: true
      client_id: cm-patch
      client_secret: unused
      ssl_verify: false
      discovery: https://verifier.seller.com/services/cm-patch/.well-known/openid-configuration
    opa:
      host: http://localhost:8181
      policy: policy/main
      # Note: Set this if the pap policy is set scoped to service
      # policy: ffffffffff/main
      with_body: true
```

> **Note**:
> Although the `apisix` API can be used to apply this configuration, using the
> deployment values is recommended so that the configuration remains declarative
> and is automatically restored when the deployment is recreated.
