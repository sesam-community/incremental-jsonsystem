[![Build Status](https://travis-ci.org/sesam-community/incremental-jsonsystem.svg?branch=master)](https://travis-ci.org/sesam-community/incremental-jsonsystem)
# incremental-jsonsystem
An example of system config: 

```json
{
  "_id": "incremental-jsonsystem_id",
  "type": "system:microservice",
  "connect_timeout": 60,
  "docker": {
    "environment": {
      "URL_PATTERN": "http://external-host:8888/__PATH__?offset=__since__&limit=__limit__",
      "AUTHENTICITION": "oauth2",
      "CONFIG": {
        "oauth2": {
          "client_id": "id",
          "client_secret": "secret",
          "resource": "resource",
          "token_url": "url"
        },
        "..": ".."
      },
      "UPDATED_PROPERTY": "sequenceNumber"
    },
    "image": "sesam/incremental-jsonsystem",
  },
  "read_timeout": 7200,
}
```

This microservice is used to support incremental Sesam json protocal when the external system dont support it. We will add one property *_updated* whose value is copied from *updated_property*.

A pipe send a request to the microservice, such as "http://incremental-urlsystem:5000/relative_path". The request will be forward to a new url defined in URL_PATTERN. The optional variables in URL_PATTERN are:
  - \_\_path\_\_: the relative path of the request
  - \_\_since\_\_: the since parameter gotten from the request
  - \_\_limit\_\_: the limit parameter gotten from the request. If the web service don't support limit, we will sort the response and only return top entities back.


Supported authentication method:
  - if it is empty, we use it as an url service without any authentication method
  - oauth2
