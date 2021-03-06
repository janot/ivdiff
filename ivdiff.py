import logging
import requests
import re
from lxml import etree
from io import StringIO
import difflib
import webbrowser
import os
import argparse
from urllib.parse import urlparse
from http.cookies import SimpleCookie
from hashlib import md5

logging.basicConfig(filename="ivdiff.log", level=logging.INFO)


def getHtml(domain, cookies, url, template):
    rules = ""
    try:
        templNumber = str(int(template))
        contest = "contest"
    except ValueError:
        la = open(template, "r", encoding='utf8')
        rules = str(la.read())
        la.close()
        contest = "my"
        templNumber = ""

    if contest == "my":
        d = "https://instantview.telegram.org/{}/{}".format(contest, domain)
    else:
        d = "https://instantview.telegram.org/{}/{}/template{}".format(contest, domain, templNumber)
    logging.info("-- Getting html for {} --".format(url))
    r = requests.get(d, cookies=cookies, params=dict(url=url))

    hash = re.search("{}\\?hash=(.*?)\",".format(contest), str(r.content)).group(1)
    logging.info("hash={}".format(hash))

    rules = rules.encode('utf-8')

    r = requests.post("https://instantview.telegram.org/api/{}".format(contest), cookies=cookies, params=dict(hash=hash), data=dict(url=url, section=domain, method="processByRules", rules_id=templNumber, rules=rules, random_id=""))
    random_id = r.json()["random_id"]
    logging.info("random_id={}".format(random_id))

    final = ""
    fails = 0
    while "result_doc_url" not in final:
        logging.info("trying again... {}".format(final))
        r = requests.post("https://instantview.telegram.org/api/{}".format(contest), cookies=cookies, params=dict(hash=hash), data=dict(url=url, section=domain, method="processByRules", rules_id=templNumber, rules=rules, random_id=random_id))
        final = r.json()
        random_id = final["random_id"]

        if "status" not in final:
            # Get randomid again
            r = requests.post("https://instantview.telegram.org/api/{}".format(contest), cookies=cookies, params=dict(hash=hash), data=dict(url=url, section=domain, method="processByRules", rules_id=templNumber, rules=rules, random_id=""))
            random_id = r.json()["random_id"]
            logging.info("new random_id={}".format(random_id))
            fails += 1
            if fails >= 5:
                logging.error("uhhh trying another hash maybe")
                fails = 0
                r = requests.get(d, cookies=cookies, params=dict(url=url))
                hash = re.search("{}\\?hash=(.*?)\",".format(contest), str(r.content)).group(1)
                logging.info("new hash={}".format(hash))

    random_id = final["random_id"]
    u = final["result_doc_url"]

    logging.info("loading page {}".format(u))
    r = requests.get(u, cookies=cookies)

    if "NESTED_ELEMENT_NOT_SUPPORTED" in str(r.content):
        logging.error("NESTED_ELEMENT_NOT_SUPPORTED in {}".format(url))

    htmlparser = etree.HTMLParser(remove_blank_text=True)
    tree = etree.parse(StringIO(str(r.content)), htmlparser)

    logging.info("-- FINISHED --")

    return (d + "?url=" + url, tree)


def compare(s, f):
    # You can remove elements before diff if you want to
    #
    # for bad in s.xpath("//h6[@data-block=\"Kicker\"]"):
    #     bad.getparent().remove(bad)
    pass


def checkDiff(cookies, url, t1, t2):
    if not url.startswith("http"):
        url = "http://" + url

    domain = urlparse(url).netloc
    if domain.startswith("www."):
        domain = domain[4:]

    c = open(cookies, "r")
    cl = c.read()
    c.close()

    cookie = SimpleCookie()
    cookie.load(cl)

    cookies = {}
    for key, morsel in cookie.items():
        cookies[key] = morsel.value

    f1 = getHtml(domain, cookies, url, t1)
    s1 = getHtml(domain, cookies, url, t2)
    f = f1[1]
    s = s1[1]

    compare(f, s)

    a1 = f.xpath("//article")
    if len(a1) == 0:
        a1 = f.xpath("//section[@class=\"message\"]")
    a2 = s.xpath("//article")
    if len(a2) == 0:
        a2 = s.xpath("//section[@class=\"message\"]")

    diff = difflib.HtmlDiff(wrapcolumn=120).make_file(etree.tostring(a1[0], pretty_print=True).decode("utf-8").split("\n"), etree.tostring(a2[0], pretty_print=True).decode("utf-8").split("\n"))
    htmlparser = etree.HTMLParser(remove_blank_text=True)
    tree = etree.parse(StringIO(str(diff)), htmlparser)

    link1 = etree.Element("a", **{"href": f1[0]})
    link1.text = "Template {}\n".format(t1)

    link2 = etree.Element("a", **{"href": s1[0]})
    link2.text = "Template {}".format(t2)

    tree.xpath("//body")[0].addprevious(link1)
    tree.xpath("//body")[0].addprevious(etree.Element("br"))
    tree.xpath("//body")[0].addprevious(link2)
    tree.xpath("//body")[0].addprevious(etree.Element("br"))
    tree.xpath("//body")[0].addprevious(etree.Element("br"))

    for bad in tree.xpath("//table[@summary='Legends']"):
        bad.getparent().remove(bad)
    final = etree.tostring(tree, pretty_print=True).decode("utf-8")

    # ДУМОТЬ ВСО ЕСЧО ВПАДЛУ
    # ХТО ЗАРЖАВ СТАВ РОФЛАН ЇБАЛО
    if "class=\"diff_add\"" in final or "class=\"diff_chg\"" in final or "class=\"diff_sub\"" in final:
        md = md5()
        md.update(url.encode('utf-8'))

        fn = "gen/{}/{}_{}_{}.html".format(domain, t1, t2, str(md.hexdigest()))
        try:
            os.makedirs(os.path.dirname(fn))
        except Exception:
            pass
        file = open(fn, "w")
        file.write(final)
        file.close()
        webbrowser.open_new_tab("file:///{}/{}".format(os.getcwd(), fn))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Get pretty HTML diff between two IV templates.')
    parser.add_argument('t1', metavar='first_template', type=str, help='first template number OR template file path')
    parser.add_argument('t2', metavar='second_template', type=str, help='second template number OR template file path')
    parser.add_argument('url', metavar='url', nargs='+', type=str, help='original page url to diff')
    parser.add_argument('--cookies', '-c', help='path to file with cookies (default is cookies.txt)', nargs='?', default="cookies.txt")

    args = parser.parse_args()
    for i in args.url:
        checkDiff(args.cookies, i, args.t1, args.t2)
