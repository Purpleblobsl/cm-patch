# TODO

## cm-patch

- [ ] **Subscribe** to the TMF
- [ ] **Filter** `TMF_IGNORE_ORGS` is not used
- [ ] **Limits**:
  - [ ] If a event is thrown fails, it's _"forever"_ lost.
  - [ ] If 2 or more orders have a _"duplicated"_ resource:
    - [ ] Exactly the same `json`: It can be solved by counting...
    - [ ] Same id: Nothing can be done, but throw a error `:3`
  - [ ] Bundled resources are not handled...
  - [ ] Policies from the order specifications are not checked

## docs

- [ ] Update readme
- [ ] **Organization** document how to setup a organization callback
- [ ] **Pap** document the policy for the service to work

