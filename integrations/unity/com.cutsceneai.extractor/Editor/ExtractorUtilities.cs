using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace CutsceneAI.UnityExtractor
{
    internal static class ExtractorUtilities
    {
        internal static readonly RationalRate MicrosecondRate = new(1_000_000, 1);

        internal static RationalRate FrameRateToRational(double fps)
        {
            if (Math.Abs(fps - 23.976023976) < 0.001 || Math.Abs(fps - 23.976) < 0.001)
                return new RationalRate(24000, 1001);
            if (Math.Abs(fps - 29.97002997) < 0.001 || Math.Abs(fps - 29.97) < 0.001)
                return new RationalRate(30000, 1001);
            if (Math.Abs(fps - 59.94005994) < 0.001 || Math.Abs(fps - 59.94) < 0.001)
                return new RationalRate(60000, 1001);

            var rounded = Math.Round(fps);
            if (Math.Abs(fps - rounded) < 1e-9)
                return new RationalRate((long)rounded, 1);

            const long denominator = 1_000_000;
            var numerator = (long)Math.Round(fps * denominator);
            var gcd = GreatestCommonDivisor(Math.Abs(numerator), denominator);
            return new RationalRate(numerator / gcd, denominator / gcd);
        }

        internal static RationalTime SecondsToRationalTime(double seconds)
        {
            return new RationalTime((long)Math.Round(seconds * 1_000_000.0), MicrosecondRate);
        }

        internal static Vector3Record CanonicalPosition(Vector3 value)
        {
            return new Vector3Record { x = value.x, y = value.y, z = -value.z };
        }

        internal static Vector3Record CanonicalScale(Vector3 value)
        {
            return new Vector3Record { x = value.x, y = value.y, z = value.z };
        }

        internal static QuaternionRecord CanonicalRotation(Quaternion value)
        {
            return new QuaternionRecord { x = -value.x, y = -value.y, z = value.z, w = value.w };
        }

        internal static TransformSnapshot CaptureLocalTransform(Transform transform)
        {
            return new TransformSnapshot
            {
                position = CanonicalPosition(transform.localPosition),
                rotation = CanonicalRotation(transform.localRotation),
                scale = CanonicalScale(transform.localScale),
            };
        }

        internal static TransformSnapshot CaptureWorldTransform(Transform transform)
        {
            return new TransformSnapshot
            {
                position = CanonicalPosition(transform.position),
                rotation = CanonicalRotation(transform.rotation),
                scale = CanonicalScale(transform.lossyScale),
            };
        }

        internal static string HierarchyPath(Transform transform)
        {
            var path = transform.name;
            var current = transform.parent;
            while (current != null)
            {
                path = current.name + "/" + path;
                current = current.parent;
            }
            return path;
        }

        internal static string StableSceneObjectId(GameObject gameObject)
        {
            return "unity-object:" + GlobalObjectId.GetGlobalObjectIdSlow(gameObject);
        }

        internal static bool TryGetAssetIdentity(UnityEngine.Object asset, out string guid, out long localId, out string path)
        {
            guid = string.Empty;
            localId = 0;
            path = string.Empty;
            if (asset == null)
                return false;

            path = AssetDatabase.GetAssetPath(asset);
            if (string.IsNullOrWhiteSpace(path))
                return false;

            return AssetDatabase.TryGetGUIDAndLocalFileIdentifier(asset, out guid, out localId);
        }

        internal static string StableAssetId(UnityEngine.Object asset)
        {
            if (TryGetAssetIdentity(asset, out var guid, out var localId, out _))
                return $"unity-asset:{guid}:{localId}";

            return "unity-object:" + GlobalObjectId.GetGlobalObjectIdSlow(asset);
        }

        internal static string AssetReference(UnityEngine.Object asset)
        {
            if (asset == null)
                return string.Empty;

            if (TryGetAssetIdentity(asset, out var guid, out var localId, out var path))
                return $"{path}#{asset.name}|guid={guid}|local={localId}";

            return GlobalObjectId.GetGlobalObjectIdSlow(asset).ToString();
        }

        internal static string Sha256(string value)
        {
            using var sha = SHA256.Create();
            var bytes = sha.ComputeHash(Encoding.UTF8.GetBytes(value ?? string.Empty));
            var builder = new StringBuilder(bytes.Length * 2);
            foreach (var b in bytes)
                builder.Append(b.ToString("x2"));
            return builder.ToString();
        }

        internal static string ProjectFingerprint()
        {
            var projectRoot = Directory.GetParent(Application.dataPath)?.FullName ?? Application.dataPath;
            var normalized = Path.GetFullPath(projectRoot).Replace('\\', '/').TrimEnd('/').ToLowerInvariant();
            return "sha256:" + Sha256(normalized);
        }

        internal static string SafeFileName(string value)
        {
            foreach (var invalid in Path.GetInvalidFileNameChars())
                value = value.Replace(invalid, '_');
            return value;
        }

        internal static double ConvertCurveValueToCanonical(string propertyName, double value, out string semantic, out string conversion)
        {
            semantic = string.Empty;
            conversion = "identity";

            if (propertyName.EndsWith("m_LocalPosition.x", StringComparison.Ordinal) ||
                propertyName.EndsWith("localPosition.x", StringComparison.Ordinal))
            {
                semantic = "transform.position.x";
                return value;
            }
            if (propertyName.EndsWith("m_LocalPosition.y", StringComparison.Ordinal) ||
                propertyName.EndsWith("localPosition.y", StringComparison.Ordinal))
            {
                semantic = "transform.position.y";
                return value;
            }
            if (propertyName.EndsWith("m_LocalPosition.z", StringComparison.Ordinal) ||
                propertyName.EndsWith("localPosition.z", StringComparison.Ordinal))
            {
                semantic = "transform.position.z";
                conversion = "negate_z_for_right_handed_basis";
                return -value;
            }
            if (propertyName.EndsWith("m_LocalRotation.x", StringComparison.Ordinal) || propertyName.EndsWith("localRotation.x", StringComparison.Ordinal))
            {
                semantic = "transform.rotation.x";
                conversion = "negate_xy_for_right_handed_basis";
                return -value;
            }
            if (propertyName.EndsWith("m_LocalRotation.y", StringComparison.Ordinal) || propertyName.EndsWith("localRotation.y", StringComparison.Ordinal))
            {
                semantic = "transform.rotation.y";
                conversion = "negate_xy_for_right_handed_basis";
                return -value;
            }
            if (propertyName.EndsWith("m_LocalRotation.z", StringComparison.Ordinal) || propertyName.EndsWith("localRotation.z", StringComparison.Ordinal))
            {
                semantic = "transform.rotation.z";
                return value;
            }
            if (propertyName.EndsWith("m_LocalRotation.w", StringComparison.Ordinal) || propertyName.EndsWith("localRotation.w", StringComparison.Ordinal))
            {
                semantic = "transform.rotation.w";
                return value;
            }

            if (propertyName.IndexOf("localEuler", StringComparison.OrdinalIgnoreCase) >= 0)
            {
                semantic = "transform.rotation.euler_native";
                conversion = "native_only_requires_rotation_reconstruction";
            }

            return value;
        }

        private static long GreatestCommonDivisor(long a, long b)
        {
            while (b != 0)
            {
                var t = b;
                b = a % b;
                a = t;
            }
            return a == 0 ? 1 : a;
        }
    }
}
