package com.wizaicorp.namazvakitleri.api

import android.util.Xml
import com.wizaicorp.namazvakitleri.data.Lang
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.xmlpull.v1.XmlPullParser
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

data class NewsItem(val title: String, val link: String, val source: String, val pubDate: String)

/** Google News RSS'ten dini haberler - API anahtari gerektirmez. */
object NewsRss {

    suspend fun fetch(): List<NewsItem> = withContext(Dispatchers.IO) {
        val (query, hl, gl, ceid) =
            if (Lang.code == "tr")
                listOf("diyanet OR ramazan OR kandil OR hac OR umre OR cami", "tr", "TR", "TR:tr")
            else
                listOf("islam OR ramadan OR hajj OR mosque OR eid", "en-US", "US", "US:en")
        val q = URLEncoder.encode(query, "UTF-8")
        val url = "https://news.google.com/rss/search?q=$q&hl=$hl&gl=$gl&ceid=$ceid"

        val conn = URL(url).openConnection() as HttpURLConnection
        conn.connectTimeout = 10000
        conn.readTimeout = 10000
        conn.setRequestProperty("User-Agent", "Mozilla/5.0")
        try {
            conn.inputStream.use { stream ->
                val parser = Xml.newPullParser()
                parser.setInput(stream, null)
                val items = mutableListOf<NewsItem>()
                var inItem = false
                var title = ""; var link = ""; var source = ""; var pubDate = ""
                var tag = ""
                var event = parser.eventType
                while (event != XmlPullParser.END_DOCUMENT && items.size < 30) {
                    when (event) {
                        XmlPullParser.START_TAG -> {
                            tag = parser.name
                            if (tag == "item") {
                                inItem = true
                                title = ""; link = ""; source = ""; pubDate = ""
                            }
                        }
                        XmlPullParser.TEXT -> {
                            if (inItem) {
                                val text = parser.text?.trim() ?: ""
                                if (text.isNotEmpty()) when (tag) {
                                    "title"   -> if (title.isEmpty()) title = text
                                    "link"    -> if (link.isEmpty()) link = text
                                    "source"  -> if (source.isEmpty()) source = text
                                    "pubDate" -> if (pubDate.isEmpty()) pubDate = text
                                }
                            }
                        }
                        XmlPullParser.END_TAG -> {
                            if (parser.name == "item") {
                                inItem = false
                                if (title.isNotEmpty() && link.isNotEmpty())
                                    items.add(NewsItem(title, link, source, pubDate.take(16)))
                            }
                            tag = ""
                        }
                    }
                    event = parser.next()
                }
                items
            }
        } finally {
            conn.disconnect()
        }
    }
}
