importScripts("https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.sw.js");

self.addEventListener('notificationclick', function (event)
{
  console.log("Got Event!")
    //For root applications: just change "'./'" to "'/'"
    //Very important having the last forward slash on "new URL('./', location)..."
    // const rootUrl = new URL('/', location).href; 
    event.notification.close();
    console.log(event);
    event.waitUntil(clients.openWindow(event.notification.data.launchURL));

    // event.waitUntil(
    //     clients.matchAll().then(matchedClients =>
    //     {
    //         for (let client of matchedClients)
    //         {
    //             if (client.url.indexOf(rootUrl) >= 0)
    //             {
    //                 return client.focus();
    //             }
    //         }

    //         return clients.openWindow(rootUrl).then(function (client) { client.focus(); });
    //     })
   
    // );
});