from datetime import datetime
from time import perf_counter, sleep

from pymongo import MongoClient


URI = (
    "mongodb://192.168.121.134:27117,"
    "192.168.121.134:27118,"
    "192.168.121.134:27119/"
    "?replicaSet=libraryRS"
    "&serverSelectionTimeoutMS=3000"
    "&connectTimeoutMS=3000"
    "&socketTimeoutMS=3000"
    "&retryReads=true"
    "&retryWrites=true"
)

client = MongoClient(URI)

db = client["replica_test"]
read_collection = db["replication_probe"]
write_collection = db["failover_probe"]


def now():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def primary_name():
    primary = client.primary
    if primary is None:
        return "NONE"
    return f"{primary[0]}:{primary[1]}"


print("===== TASK5 FAILOVER PROBE =====")

try:
    client.admin.command("ping")
    print(f"{now()} CONNECT OK  primary={primary_name()}")
except Exception as exc:
    print(f"{now()} CONNECT ERROR {type(exc).__name__}: {exc}")
    raise SystemExit(1)


sequence = 0

try:
    while True:
        sequence += 1

        start = perf_counter()

        try:
            doc = read_collection.find_one(
                {"test_name": "task5_replication"}
            )

            elapsed = (perf_counter() - start) * 1000

            if doc:
                print(
                    f"{now()} READ  OK    "
                    f"{elapsed:7.1f} ms  "
                    f"primary={primary_name()}"
                )
            else:
                print(
                    f"{now()} READ  EMPTY "
                    f"{elapsed:7.1f} ms  "
                    f"primary={primary_name()}"
                )

        except Exception as exc:
            elapsed = (perf_counter() - start) * 1000

            print(
                f"{now()} READ  ERROR "
                f"{elapsed:7.1f} ms  "
                f"{type(exc).__name__}: "
                f"{str(exc).splitlines()[0]}"
            )

        start = perf_counter()

        try:
            write_collection.insert_one(
                {
                    "sequence": sequence,
                    "created_at": datetime.now(),
                    "source": "task5_failover_probe",
                }
            )

            elapsed = (perf_counter() - start) * 1000

            print(
                f"{now()} WRITE OK    "
                f"{elapsed:7.1f} ms  "
                f"primary={primary_name()}"
            )

        except Exception as exc:
            elapsed = (perf_counter() - start) * 1000

            print(
                f"{now()} WRITE ERROR "
                f"{elapsed:7.1f} ms  "
                f"{type(exc).__name__}: "
                f"{str(exc).splitlines()[0]}"
            )

        sleep(1)

except KeyboardInterrupt:
    print()
    print(f"{now()} PROBE STOPPED")

finally:
    client.close()