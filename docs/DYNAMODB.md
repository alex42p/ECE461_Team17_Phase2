# Dynamo Setup

Follow all of these steps in order and you *should* be able to set up DynamoDB Local (inshallah):

1. Navigate to [this link](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/DynamoDBLocal.DownloadingAndRunning.html#docker).

2. You should see a few dropdown menus. The two that we care about are "Download DynamoDB local" and "Run DynamoDB local as Docker image." Expand both of them.

3. I have already downloaded and committed the zip file; it's underneath the "dynamodb/" folder in the root directory. Under the first dropdown, you'll see a command to run to start the DynamoDB Docker image. This command assumes you're cd'd into that directory. So instead, copy and run the command below to run the image:
```
java -Djava.library.path=./dynamodb/DynamoDBLocal_lib -jar dynamodb/DynamoDBLocal.jar -sharedDb
```

If it runs successfully, you should see something like this:

```
Initializing DynamoDB Local with the following configuration:
Port:   8000
InMemory:       false
Version:        3.1.0
DbPath: null
SharedDb:       true
shouldDelayTransientStatuses:   false
CorsParams:     null
```

If it errored, you probably saw some shit like this:
```
Error: LinkageError occurred while loading main class software.amazon.dynamodb.services.local.main.ServerRunner java.lang.UnsupportedClassVersionError: software/amazon/dynamodb/services/local/main/ServerRunner has been compiled by a more recent version of the Java Runtime (class file version 61.0), this version of the Java Runtime only recognizes class file versions up to 55.0
```

4. Assuming you saw something like the above error, you need to install a new version of Java because eceprog's version is out of date cuz IT hates us. Run:
```
java -version
```
to verify that you're running Java v11 or something super outdated. If that's the case, you need to manually install an updated version of Java v17.  

5. Go to [this link](https://github.com/adoptium/temurin17-binaries/releases/tag/jdk-17.0.17%2B10), and Ctrl+F "OpenJDK17U-jdk_x64_linux_hotspot_17.0.17_10.tar.gz". Download that file. Copy-paste is into the root directory on the Shay server (e.g. pieta@eceprog5: ~/).

6. Once you have the tar.gz file in your Shay root directory, run this command to extract it:
```
tar -xzf OpenJDK17U-jdk_x64_linux_hotspot_17.0.17_10.tar.gz
```
After that you can run `ls -a` to make sure that you have a `jdk-17.0.17+10/` folder.

7. Now that you've extracted the file, go into your ~/.bashrc file with `vi ~/.bashrc`, and paste this at the VERY bottom of it: 
```
export JAVA_HOME="$HOME/jdk-17.0.17+10"
export PATH="$JAVA_HOME/bin:$PATH"
```
Once you've pasted this, save and quit (ESC+`:wq`), and run `source ~/.bashrc`. Your Java version should be updated now.

8. Run `java -version` to confirm, and it should say something like this: `openjdk version "17.0.17" 2025-10-21`

9. If the above is true, try rerunning the command from step #3 to verify that you get the successful output. 

10. That's the extent of what I've done so far. When you look in the second dropdown menu from the linked setup AWS documentation, I *did* create the docker-compose.yml file in our project root directory that should allegedly start the DynamoDB instance every time it's run. The rest is up to you.
