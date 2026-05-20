#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# MainActivity.kt + AndroidBridge — loadLeaderboard ekleme
# Calistir: python3 ~/fix_04_leaderboard_load.py

FILE = "/data/data/com.termux/files/home/tank-siege/app/src/main/java/com/wizaicorp/tanksiege/MainActivity.kt"

patches = [
    # 1. LeaderboardVariant importu ekle (mevcut import blogunun sonuna)
    (
        "import com.google.android.gms.games.snapshot.Snapshot\n",
        "import com.google.android.gms.games.snapshot.Snapshot\n"
        "import com.google.android.gms.games.leaderboard.LeaderboardVariant\n"
    ),

    # 2. MainActivity'e loadLeaderboard() fonksiyonu ekle (showLeaderboard'dan sonra)
    (
        "    fun signOut() {",
        '''    fun loadLeaderboard(boardId: String, kind: String) {
        if (!isSignedIn) {
            handler.post {
                webView.evaluateJavascript("TSLB.receiveData('$kind',null,'not_signed_in');", null)
            }
            return
        }
        PlayGames.getLeaderboardsClient(this)
            .loadTopScores(boardId,
                LeaderboardVariant.TIME_SPAN_ALL_TIME,
                LeaderboardVariant.COLLECTION_PUBLIC, 25)
            .addOnSuccessListener { annotated ->
                val scores = annotated.get()
                if (scores == null) {
                    annotated.release()
                    handler.post {
                        webView.evaluateJavascript("TSLB.receiveData('$kind',null,'no_data');", null)
                    }
                    return@addOnSuccessListener
                }
                val buf = scores.scores
                val sb = StringBuilder("[")
                for (i in 0 until buf.count) {
                    val e = buf.get(i)
                    if (i > 0) sb.append(",")
                    val name = e.scoreHolderDisplayName
                        .replace("\\\\", "\\\\\\\\")
                        .replace("\"", "\\\\\"")
                        .replace("'", "\\\\'")
                    sb.append("""{"rank":${e.rank},"name":"${'$'}{name}","score":${e.rawScore}}""")
                }
                sb.append("]")
                buf.release()
                annotated.release()
                val json = sb.toString()
                handler.post {
                    webView.evaluateJavascript("TSLB.receiveData('$kind',${'$'}{json},'');", null)
                }
            }
            .addOnFailureListener {
                handler.post {
                    webView.evaluateJavascript("TSLB.receiveData('$kind',null,'failed');", null)
                }
            }
    }

    fun signOut() {'''
    ),

    # 3. AndroidBridge'e @JavascriptInterface ekle (showLeaderboard bridge'inden sonra)
    (
        "    @JavascriptInterface fun trySilentSignIn() {",
        "    @JavascriptInterface fun loadLeaderboard(boardId: String, kind: String) {\n"
        "        handler.post { activity.loadLeaderboard(boardId, kind) }\n"
        "    }\n"
        "    @JavascriptInterface fun trySilentSignIn() {"
    ),
]

with open(FILE, "r", encoding="utf-8") as f:
    content = f.read()

original = content
for i, (old, new) in enumerate(patches, 1):
    count = content.count(old)
    if count == 0:
        print(f"  BULUNAMADI - Patch {i}")
    else:
        content = content.replace(old, new, 1)
        print(f"  OK - Patch {i}")

if content == original:
    print("Degisiklik yapilmadi.")
    import sys; sys.exit(1)

with open(FILE, "w", encoding="utf-8") as f:
    f.write(content)
print("Kaydedildi.")
