# incremental-urlsystem
sesam Http->Ftp microservice

An example of system config: 

```json
{
  "_id": "incremental-jsonsystem",
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
          "resource": "resource"
          "token_url": "url"
        },
        "..": ".."
      }
      "UPDATED_PROPERTY": "sequenceNumber"
    },
    "image": "sesam/incremental-urlsystem",
  },
  "read_timeout": 7200,
}
```

This microservice should support incremental Sesam json protocal. We will add one property *_updated* whose value is copied from updated_property.

Node send a request, such as "http://incremental-urlsystem:5000/path". The request will be forward to a new url defined in URL_PATTERN. The optional variables in URL_PATTERN are:
  - __path__: the relative path in the request
  - __since__: the since parameter gotten from the request
  - __limit__: the limit parameter gotten from the request. If the web service don't support limit, we will sort the response and only return top entities back.


Supported authentication method:
  - None
  - oauth2
