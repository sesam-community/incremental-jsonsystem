[![Build Status](https://travis-ci.org/sesam-community/incremental-jsonsystem.svg?branch=master)](https://travis-ci.org/sesam-community/incremental-jsonsystem)

# incremental-jsonsystem
proxy microservice that implements [SESAM pull protocol](https://docs.sesam.io/json-pull.html#requests) on a json source system.

can be used to:
 * implement support for sesam's _since_ parameter
 * extract entities from a field in response json
 * add sesam's \_updated field to support continuation
 * sorting after \_updated field value to support chronological continuation
 * limit the number of returned entities


### Environment Parameters

| CONFIG_NAME        | DESCRIPTION           | IS_REQUIRED  |DEFAULT_VALUE|
| -------------------|---------------------|:------------:|:-----------:|
| FULL_URL_PATTERN | pattern for the full run url. see URL_PATTERN below. | yes | n/a |
| UPDATED_URL_PATTERN |  pattern for the incremental run url. see URL_PATTERN below. | yes | n/a |
| CONFIG | json with optional _headers_ and optional _oauth2_ fields which are also json. | yes | n/a |
| AUTHENTICATION | OAUTH2 for oauth2 support. Any other value for no auth | no | n/a |
| UPDATED_PROPERTY | (DEPRECATED) use corresponding query parameter instead. | no | n/a |
| OFFSET_BIGGER_AND_EQUAL | (DEPRECATED) use corresponding query parameter instead.| no | n/a |


### Query Parameters

Query parameters that the service supports can be divided into three groups:

#### 1. query parameters after SESAM pull protocol
These parameters are supported due to SESAM pull protocol. Note that these parameters are sent implicitly by the SESAM depending on the continuation support setings in the pipe config.

| CONFIG_NAME        | DESCRIPTION           | IS_REQUIRED  |DEFAULT_VALUE|
| -------------------|---------------------|:------------:|:-----------:|
| since | see [SESAM pull protocol](https://docs.sesam.io/json-pull.html#requests) | no | n/a |
| limit | see [SESAM pull protocol](https://docs.sesam.io/json-pull.html#requests)  | no | n/a |

#### 2. query parameters after proxy service:
There are the parameters that effect the way this microservice works. They are all prefixed with "ms_".

| CONFIG_NAME        | DESCRIPTION           | IS_REQUIRED  |DEFAULT_VALUE|
| -------------------|---------------------|:------------:|:-----------:|
| ms_since_param_at_src | the name of the query parameter at the source system that corresponds to sesam's _limit_ parameter | no | n/a |
| ms_limit_param_at_src | the name of the query parameter at the source system that corresponds to sesam's _limit_ parameter | no | n/a |
| ms_updated_property | the name of the field that will be read into \_updated field for each entity | yes | n/a |
| ms_data_property | the name of the field from which the entities will be read from  | no | n/a |
| ms_do_sort | flag to get output sorted after \_updated field. Values: _true_/_false_ | no | _false_ |
| ms_offset_bigger_and_equal | set to _true_ to get the entities that are _greater than_ the offset value instead of _greater-than-or-equals_. The source systems behaviour should be taken into account here. Works for offset values of type integer only. Values: _true_/_false_ | no | _false_ |

#### 3. query parameters after the Source system
There are the parameters that are passed over to the source system.



### An example of system config:

system:
```json
{
  "_id": "incremental-jsonsystem_id",
  "type": "system:microservice",
  "connect_timeout": 60,
  "docker": {
    "environment": {
      "URL_PATTERN": "http://external-host:8888/__PATH__?offset=__since__&limit=__limit__",
      "AUTHENTICATION": "oauth2",
      "CONFIG": {
        "oauth2": {
          "client_id": "id",
          "client_secret": "secret",
          "resource": "resource",
          "token_url": "url"
        },
        "headers": {
          "x-api-version": "1.0"
        },
      "UPDATED_PROPERTY": "sequenceNumber"
    },
    "image": "sesamcommunity/incremental-jsonsystem",
    "port": 5000
  },
  "read_timeout": 7200,
}
```
system and pipe
```json
{
  "_id": "incremental-jsonsystem_id",
  "type": "system:microservice",
  "connect_timeout": 60,
  "docker": {
    "environment": {
      "URL_PATTERN": "http://external-host:8888/__PATH__",
      "AUTHENTICATION": "oauth2",
      "CONFIG": {
        "oauth2": {
          "client_id": "id",
          "client_secret": "secret",
          "resource": "resource",
          "token_url": "url"
        },
        "headers": {
          "x-api-version": "1.0"
        }
    },
    "image": "sesamcommunity/incremental-jsonsystem:v2.0",
    "port": 5000
  },
  "read_timeout": 7200,
}

{
  "_id": "Copy of kundemaster-customer",
  "type": "pipe",
  "source": {
    "type": "json",
        "system": "incremental-jsonsystem_id",
        "is_chronological": true,
        "is_since_comparable": true,
        "supports_since": true,
        "url": "mypath/yourpath/ourpath?ms_since_param_at_src=updated_since&ms_updated_property=updated_at&ms_do_sort=true"      
  },
  "transform":  [...]
}

```


 #### URL_PATTERN
 A valid URL_PATTERN is any template string that will reveal a url after optionally being exposed to several predefined  replacements.

 It should suffice to use only \_\_path\_\_ replacement in most cases. In case not, you can use other replacements described here.

 Replacements :

  - \_\_path\_\_: Will be replaced with the path int the _url_ field of the input pipe
  - \_\_since\_\_: Will be replaced with the _since_ value that is sent by SESAM upon pipe execution. (applicable to pipes with continuation support)
  - \_\_limit\_\_: Will be replaced with the _since_ value that is sent by SESAM upon pipe execution.

 examples
  * ENV(my-base-url)/\_\_path\_\_
  * ENV(my-base-url)/\_\_path\_\__/\_\_since\_\_
  * ENV(my-base-url)/\_\_path\_\_?since=\_\_since\_\_
  * ENV(my-base-url)/\_\_path\_\_?since=\_\_since\_\_&pagesize=\_\_limit\_\_
