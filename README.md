# awscli_tools

Some Python and shell scripts to do things with AWS CLI stuff

## Crib Sheet

### How do I see the contents of a 'folder'?

Include a final `/`, otherwise it will only tell you which prefixes exist that start with the name of the folder.
For an object named `prefix1/prefix2/name.ext` stored in the bucket `bucket1`.
```
> aws s3 ls s3://bucket1/prefix1
      PRE   prefix1
> aws s3 ls s3://bucket1/prefix1/
      PRE   prefix2
> aws s3 ls s3://bucket1/prefix1/ --recursive
date  size  prefix1/prefix2/name.ext
```

#### A longer explanation about folders and prefixes

There are no `folders` in S3. Instead, the entire path is treated as a very long file name, e.g. a file `name.ext` stored in the folder `prefix1` gets the object name `prefix1/name.ext`.
To retain some of the utility of folder heirarchies, AWS CLI parses every string that ends with `/` as a 'prefix'.
Prefixes behave similar, but not the same as a folder path.

For example, these two file paths are parsed identically, `/Users/username//Downloads` and `/Users/username/Downloads` because the doubled `/` is treated as a single separator.
These two object names are not the same `/Users/username//Downloads/` and `/Users/username/Downloads/` becuase the second `/` is treated as its own prefix.

```
> aws s3 ls s3://bucket1/Users/username/
      PRE   /
      PRE   Downloads/
```

### How do I use a wildcard in a list command?

The `aws s3 ls` command does not have wildcard support.
The easiest way to replicate this is to pipe the results to `grep`.
You will have to develop regular expressions that are more precise since `.*` will match across folder separators.

```
> ls ~/Downloads/*.pdf
      some.pdf
> aws s3 ls s3://bucket1/Downloads/ | grep ".pdf"
      some.pdf
```


### How do I get the size of a bucket?

Add `--summarize` to an `aws s3 ls --recursive` command.
```
> aws s3 ls --recursive --summarize s3://bucket1
Total Objects: ####
   Total Size: ####
```

This also works with prefixes.
```
> aws s3 ls --recursive --summarize s3://bucket1/prefix1/
Total Objects: ###
   Total Size: ###
```

You can add `--human-readable` converts the total size to binary 1000's (i.e. tebibytes).
Personal preference, but avoid.

### How do I know the storage class used for a file?

Use the `list-objects-v2` method that's part of `s3api`.
Note, the syntax for methods in `s3api` is different from `s3`
For an object named `prefix1/prefix2/name.ext` stored in the bucket `bucket1`

```
> aws s3api list-objects-v2 --bucket bucket1 --prefix prefix1 
{
    "Contents": [
        {
            "Key": "prefix1/prefix2/name.ext",
            "LastModified": "yyyy-mm-dd...",
            "ETag": "\"...\"",
            "Size": ###
            "StorageClass": "..."
        },
        ...
    ]
}
```

### How do I delete things?

To delete one thing, use the `aws s3 rm` command.

```
> aws s3 rm s3://bucket1/prefix1/name.ext
deleting: prefix1/name.ext
```  
      
To delete everything in a bucket or prefix, add the `--recursive` argument.

```
> aws s3 rm --recursive s3://bucket1/prefix1/
deleting: prefix1/name.ext
```  

To delete more than one thing but not everything in a bucket or prefix, add `--exclude` and `--include` arguments.
Always start with `--exclude '\*'` and then add the files you want to delete by including wildcard patterns.

```
> aws s3 rm --recursive --exclude '\*' --include '\*.ext' 's3://bucket1/prefix1/
deleting: prefix1/name.ext
```  

