using Acme.Data;
using Newtonsoft.Json;
using System;

namespace Acme.Core
{
    public static class Util
    {
        public static int Yoink() => Store.Get();
        public static string Ser() => JsonConvert.SerializeObject(Yoink());
    }
}
